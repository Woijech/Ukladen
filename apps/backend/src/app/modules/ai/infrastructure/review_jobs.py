"""Durable opt-in review dispatch, single-attempt execution and atomic inbox delivery."""

import json
import logging
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.core.logging import log_failure
from app.modules.ai.application.recovery import stop_run
from app.modules.ai.application.review_evidence import digest
from app.modules.ai.application.reviews import ReviewConfiguration, review_slots
from app.modules.ai.domain.connections import ConnectionUnavailable
from app.modules.ai.domain.state import AiConflict, AiNotFound, Conversation, Message, Run
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.retention import lock_owner
from app.modules.ai.infrastructure.review_collection import collect_review
from app.modules.ai.infrastructure.review_generation import bounded_briefing
from app.modules.ai.infrastructure.review_models import ReviewModel, ReviewSettingsModel
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.notifications import Notification
from app.modules.notifications.infrastructure.repository import SqlAlchemyNotificationRepository
from app.modules.users.infrastructure.repository import (
    SqlAlchemyProfileRepository,
    SqlAlchemyUserAuthentication,
)

logger = logging.getLogger(__name__)

TITLES = {
    "daily": "Ежедневный обзор AI",
    "weekly": "Недельный обзор AI",
    "warnings": "Важные изменения AI",
}


def summary_key(evidence):
    facts = {
        key: value
        for key, value in evidence.data.items()
        if key not in ("checked_at", "ends_at", "free_work_minutes")
    }
    return digest({"facts": facts, "issues": evidence.issues, "warnings": evidence.warnings})


class ReviewJobs:
    def __init__(self, service, reader, generator, *, enabled=lambda: False):
        self.service, self.reader, self.generator, self.enabled = (
            service,
            reader,
            generator,
            enabled,
        )
        self.sessions = reader.sessions

    def scan(self):
        if not self.enabled():
            return []
        now = self.service.now()
        with self.sessions() as database:
            owners = list(
                database.scalars(
                    select(ReviewSettingsModel.user_id)
                    .where(
                        ReviewSettingsModel.next_scan_at <= now,
                        ReviewSettingsModel.configuration["enabled"].as_boolean(),
                    )
                    .order_by(ReviewSettingsModel.next_scan_at, ReviewSettingsModel.user_id)
                    .limit(50)
                )
            )
        for user_id in owners:
            with self.sessions.begin() as database:
                if not lock_owner(database, user_id):
                    continue
                row = database.get(ReviewSettingsModel, user_id, populate_existing=True)
                if row is None or row.next_scan_at > now:
                    continue
                row.next_scan_at = now + timedelta(minutes=5)
                configuration = ReviewConfiguration.model_validate(row.configuration)
                profile = SqlAlchemyProfileRepository(database).get_active(user_id)
                if profile is None or not configuration.enabled:
                    continue
                repository = SqlAlchemyAiRepository(database)
                try:
                    selection, offering = self.service.connection_access().select(
                        repository, user_id, configuration.offering_id, configuration.connection_id
                    )
                    if selection.offering_version != row.offering_version:
                        raise AiConflict("Review model profile changed.")
                except AiConflict, AiNotFound, ConnectionUnavailable, ValueError:
                    row.state = row.state | {"paused": "connection_unavailable"}
                    continue
                # Connection errors are handled below without credential/model fallback.
                try:
                    with database.begin_nested():
                        evidence = collect_review(
                            database, self.reader, user_id, configuration, now
                        )
                except Exception as error:
                    log_failure(logger, "ai.review_collection_failed", error)
                    row.state = row.state | {"paused": "sources_unavailable"}
                    continue
                if row.state.get("paused") in ("connection_unavailable", "sources_unavailable"):
                    row.state = {key: value for key, value in row.state.items() if key != "paused"}
                current = [digest(issue) for issue in evidence.issues]
                known = set(row.state.get("issues", []))
                changed = set(current) - known
                # Forget resolved problems so a later recurrence can notify again.
                row.state = row.state | {"issues": [value for value in current if value in known]}
                summary_queued = False
                for kind, slot in review_slots(configuration, now, profile.timezone).items():
                    if kind == "warnings":
                        if not changed or summary_queued:
                            continue
                        slot = digest(sorted(changed))
                    elif not evidence.actionable or row.state.get(kind) == summary_key(evidence):
                        continue
                    exists = database.scalar(
                        select(ReviewModel.id).where(
                            ReviewModel.user_id == user_id,
                            ReviewModel.configuration_version == row.version,
                            ReviewModel.kind == kind,
                            ReviewModel.slot == slot,
                        )
                    )
                    if exists:
                        continue
                    identifier, conversation_id = uuid4(), uuid4()
                    repository.create_conversation(
                        Conversation(
                            id=conversation_id,
                            user_id=user_id,
                            title=TITLES[kind],
                            created_at=now,
                            offering_id=selection.offering_id,
                            offering_version=selection.offering_version,
                            connection_id=selection.connection_id,
                            provider=offering.provider,
                            model=offering.model,
                        )
                    )
                    database.add(
                        ReviewModel(
                            id=identifier,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            configuration_version=row.version,
                            kind=kind,
                            slot=slot,
                            snapshot=digest(evidence.payload()),
                            configuration=configuration.model_dump(mode="json"),
                            issue_state=current,
                            created_at=now,
                            expires_at=now + timedelta(days=30),
                        )
                    )
                    summary_queued |= kind != "warnings"
        return self.pending()

    def pending(self):
        if not self.enabled():
            return []
        with self.sessions() as database:
            return list(
                database.scalars(
                    select(ReviewModel.id)
                    .where(
                        ReviewModel.status == "queued", ReviewModel.expires_at > self.service.now()
                    )
                    .order_by(ReviewModel.created_at, ReviewModel.id)
                    .limit(50)
                )
            )

    def current(self, database, identifier, *, status="running"):
        row = database.get(ReviewModel, identifier, populate_existing=True)
        if row is None:
            raise AiNotFound()
        if not SqlAlchemyUserAuthentication(database).lock_active(row.user_id):
            raise AiConflict("Review owner is unavailable.")
        database.refresh(row)
        settings = database.get(ReviewSettingsModel, row.user_id, populate_existing=True)
        if (
            not self.enabled()
            or row.status != status
            or row.expires_at <= self.service.now()
            or (
                row.started_at is not None
                and row.started_at + timedelta(seconds=60) <= self.service.now()
            )
        ):
            raise AiConflict("Review is no longer active.")
        if settings is None or settings.version != row.configuration_version:
            raise AiConflict("Review configuration changed.")
        configuration = ReviewConfiguration.model_validate(settings.configuration)
        if not configuration.enabled:
            raise AiConflict("Reviews are disabled.")
        repository = SqlAlchemyAiRepository(database)
        conversation = repository.get_conversation(row.user_id, row.conversation_id)
        if conversation is None:
            raise AiNotFound()
        offering, _ = self.service.connection_access().check(
            repository, row.user_id, conversation, self.service.now()
        )
        evidence = collect_review(database, self.reader, row.user_id, configuration, row.created_at)
        if digest(evidence.payload()) != row.snapshot:
            raise AiConflict("Review inputs changed.")
        return row, settings, repository, offering, evidence

    def check(self, identifier):
        with self.sessions.begin() as database:
            row, _, repository, _, _ = self.current(database, identifier)
            run = repository.get_run(row.user_id, row.run_id)
            if run is None or run.status != "running":
                raise AiConflict("Review execution stopped.")

    def process(self, identifier: UUID):
        if not self.enabled():
            return
        try:
            with self.sessions.begin() as database:
                candidate = database.get(ReviewModel, identifier)
                if candidate is None or not lock_owner(database, candidate.user_id):
                    return
                database.refresh(candidate)
                if candidate.status != "queued":
                    return
                row, settings, repository, offering, evidence = self.current(
                    database, identifier, status="queued"
                )
                now = self.service.now()
                known = set(settings.state.get("issues", []))
                evidence = replace(
                    evidence,
                    issues=tuple(issue for issue in evidence.issues if digest(issue) not in known),
                )
                if row.kind == "warnings" and not evidence.issues:
                    row.status, row.finished_at = "cancelled", now
                    return
                text, sources = bounded_briefing(evidence, row.kind, offering.max_input_bytes)
                if row.kind == "warnings" and not json.loads(text)["issues"]:
                    raise AiConflict("Selected model budget cannot fit a warning.")
                self.service.access_policy.admit(row.user_id, repository, now)
                run = Run(
                    id=uuid4(),
                    user_id=row.user_id,
                    conversation_id=row.conversation_id,
                    submission_id=row.id,
                    request_digest=row.snapshot,
                    provider=offering.provider,
                    model=offering.model,
                    status="queued",
                    created_at=now,
                    updated_at=now,
                    offering_id=offering.id,
                    offering_version=offering.version,
                    connection_id=ReviewConfiguration.model_validate(
                        settings.configuration
                    ).connection_id,
                    price=offering.price,
                )
                repository.create_run(run)
                run = run.transition("running", now)
                repository.save_run(run, "queued")
                row.status, row.started_at, row.run_id = "running", now, run.id
            result = self.generator.generate(run, text, lambda: self.check(identifier))
            with self.sessions.begin() as database:
                row, settings, repository, _, published_evidence = self.current(
                    database, identifier
                )
                current = repository.get_run(row.user_id, run.id)
                if current is None or current.status != "running":
                    raise AiConflict("Review execution stopped.")
                now = self.service.now()
                repository.append_message(
                    Message(
                        id=uuid4(),
                        user_id=row.user_id,
                        conversation_id=row.conversation_id,
                        sequence=1,
                        role="assistant",
                        content=result,
                        created_at=now,
                        sources=sources,
                    )
                )
                repository.save_run(current.transition("completed", now), "running")
                row.status, row.finished_at = "completed", now
                delivered = [digest(issue) for issue in json.loads(text)["issues"]]
                known = set(settings.state.get("issues", [])) | set(delivered)
                settings.state = {
                    key: value for key, value in settings.state.items() if key != "paused"
                } | {
                    "issues": [item for item in row.issue_state if item in known],
                    row.kind: summary_key(published_evidence),
                }
                NotificationService(
                    SqlAlchemyNotificationRepository(database),
                    SqlAlchemyUserAuthentication(database),
                ).publish(
                    Notification(
                        id=uuid4(),
                        user_id=row.user_id,
                        kind="ai_review",
                        review_id=row.id,
                        title=TITLES[row.kind],
                        created_at=now,
                    )
                )
        except Exception as error:
            log_failure(logger, "ai.review_execution_failed", error)
            self.fail(identifier)

    def fail(self, identifier):
        # Unknown provider outcomes are terminal: recovery never repeats a potentially paid call.
        with self.sessions.begin() as database:
            row = database.get(ReviewModel, identifier)
            if row is None or not lock_owner(database, row.user_id):
                return
            database.refresh(row)
            if row.status not in ("queued", "running"):
                return
            repository = SqlAlchemyAiRepository(database)
            run = repository.get_run(row.user_id, row.run_id) if row.run_id else None
            now = self.service.now()
            if run is not None and run.status in ("queued", "running", "interrupted"):
                stop_run(repository, run, now, status="failed", error="unavailable")
            row.status, row.finished_at = "failed", now
            settings = database.get(ReviewSettingsModel, row.user_id, populate_existing=True)
            if settings is not None and settings.version == row.configuration_version:
                settings.state = settings.state | {"paused": "generation_unavailable"}

    def recover(self):
        now = self.service.now()
        with self.sessions() as database:
            abandoned = list(
                database.scalars(
                    select(ReviewModel.id)
                    .where(
                        ReviewModel.status == "running",
                        ReviewModel.started_at <= now - timedelta(seconds=60),
                    )
                    .limit(100)
                )
            )
        for identifier in abandoned:
            self.fail(identifier)
        expire_reviews(self.sessions, now)


def expire_reviews(sessions, now):
    with sessions() as database:
        expired = list(
            database.execute(
                select(
                    ReviewModel.user_id,
                    ReviewModel.id,
                    ReviewModel.conversation_id,
                    ReviewModel.discussed,
                )
                .where(ReviewModel.expires_at <= now)
                .limit(100)
            )
        )
    for user_id, identifier, conversation_id, _discussed in expired:
        with sessions.begin() as database:
            if not lock_owner(database, user_id):
                continue
            row = database.get(ReviewModel, identifier, populate_existing=True)
            if row is None or row.expires_at > now:
                continue
            if not row.discussed:
                repository = SqlAlchemyAiRepository(database)
                run = repository.active_run(user_id, conversation_id)
                if run is not None:
                    stop_run(repository, run, now, status="cancelled", error="cancelled")
                repository.delete_conversation(user_id, conversation_id)
            else:
                database.execute(delete(ReviewModel).where(ReviewModel.id == identifier))
