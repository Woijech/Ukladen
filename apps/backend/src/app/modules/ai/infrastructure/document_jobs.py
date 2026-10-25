import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ai.application.documents import DocumentStep
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.application.recovery import stop_run
from app.modules.ai.domain.connections import ConnectionLimited
from app.modules.ai.domain.state import AiConflict, AiNotFound, Message
from app.modules.ai.infrastructure.document_models import DocumentJobModel
from app.modules.ai.infrastructure.orm import RunModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.search.domain.evidence import SourceReference
from app.modules.search.infrastructure.source_documents import SqlAlchemySourceDocuments
from app.modules.users.infrastructure.orm import UserModel


class SqlAlchemyDocumentSteps:
    def __init__(
        self, sessions: sessionmaker[Session], service: AiService, *, now=lambda: datetime.now(UTC)
    ):
        self.sessions, self.service, self.now = sessions, service, now

    def candidates(self) -> list[UUID]:
        with self.sessions() as database:
            return list(
                database.scalars(
                    select(DocumentJobModel.run_id)
                    .join(RunModel, RunModel.id == DocumentJobModel.run_id)
                    .where(
                        RunModel.status.in_(("queued", "running")),
                        DocumentJobModel.phase.in_(("reading", "combining")),
                        (
                            DocumentJobModel.lease_until.is_(None)
                            | (DocumentJobModel.lease_until <= self.now())
                        ),
                    )
                    .order_by(RunModel.created_at, RunModel.id)
                    .limit(100)
                )
            )

    def current(self, database: Session, run_id: UUID, *, lease: UUID | None = None):
        owner = database.scalar(
            select(DocumentJobModel.user_id).where(DocumentJobModel.run_id == run_id)
        )
        if owner is None:
            return None
        owner_status = database.scalar(
            select(UserModel.status).where(UserModel.id == owner).with_for_update()
        )
        repository = SqlAlchemyAiRepository(database)
        run = repository.get_run(owner, run_id)
        job = database.get(DocumentJobModel, run_id, with_for_update=True)
        if owner_status != "active":
            if job is not None and run is not None and run.status in ("queued", "running"):
                job.phase, job.error, job.notes = "failed", "owner_unavailable", []
                job.lease, job.lease_until = None, None
                stop_run(repository, run, self.now(), status="failed", error="interrupted")
            return None
        if (
            job is None
            or run is None
            or run.status not in ("queued", "running")
            or (
                lease is not None
                and (job.lease != lease or job.lease_until is None or job.lease_until <= self.now())
            )
        ):
            return None
        try:
            self.service.conversation(repository, owner, job.conversation_id)
        except AiNotFound:
            stop_run(repository, run, self.now(), status="failed", error="interrupted")
            return None
        sources = SqlAlchemySourceDocuments(database)
        for item in job.manifest:
            identity = sources.identity(owner, item["source"], UUID(item["id"]))
            if identity is None or identity[0] != item["version"]:
                job.notes, job.phase, job.error = [], "failed", "source_changed_or_unavailable"
                job.lease, job.lease_until = None, None
                stop_run(repository, run, self.now(), status="failed", error="interrupted")
                return None
        return job, run, repository

    def claim(self, run_id: UUID) -> DocumentStep | None:
        with self.sessions.begin() as database:
            current = self.current(database, run_id)
            if current is None:
                return None
            job, run, repository = current
            now = self.now()
            if job.lease_until and job.lease_until > now:
                return None
            if job.lease is not None:
                job.failures += 1
                if job.failures >= 3:
                    job.phase, job.error, job.notes = "failed", "processing_interrupted", []
                    stop_run(repository, run, now, status="failed", error="interrupted")
                    return None
            # A crashed call has unknown usage; close it before retrying the same durable step.
            for attempt in repository.attempts(run.user_id, run.id):
                if attempt.status == "started":
                    from dataclasses import replace

                    repository.save_attempt(
                        replace(
                            attempt, status="interrupted", finished_at=now, error_code="interrupted"
                        )
                    )
            if run.status == "queued":
                run = run.transition("running", now)
                repository.save_run(run, "queued")
            if not job.manifest:
                manifest = []
                for source, ids in (
                    ("page", job.selection.get("page_ids", [])),
                    ("material", job.selection.get("material_ids", [])),
                ):
                    for identifier in dict.fromkeys(ids):
                        if source == "material" and SqlAlchemySourceDocuments(
                            database
                        ).needs_locations(run.user_id, UUID(identifier)):
                            job.lease_until = now + timedelta(seconds=5)
                            return None
                        document = SqlAlchemySourceDocuments(database).read(
                            run.user_id, source, UUID(identifier)
                        )
                        if document is None:
                            if source == "material" and SqlAlchemySourceDocuments(
                                database
                            ).material_state(run.user_id, UUID(identifier)) in (
                                "uploading",
                                "pending",
                                "processing",
                            ):
                                job.lease_until = now + timedelta(seconds=5)
                                return None
                            job.phase, job.error = "failed", "source_not_ready_or_unavailable"
                            stop_run(repository, run, now, status="failed", error="unavailable")
                            return None
                        manifest.append(
                            {
                                "source": source,
                                "id": identifier,
                                "version": document.version,
                                "title": document.title,
                                "characters": len(document.text),
                            }
                        )
                job.manifest, job.total_characters = (
                    manifest,
                    sum(item["characters"] for item in manifest),
                )
            while job.source_index < len(job.manifest):
                item = job.manifest[job.source_index]
                if job.offset >= item["characters"]:
                    job.source_index += 1
                    job.offset = 0
                    continue
                document = SqlAlchemySourceDocuments(database).read(
                    run.user_id, item["source"], UUID(item["id"])
                )
                if document is None or document.version != item["version"]:
                    raise AiConflict("Source changed before processing.")
                fragment = (
                    document.text[job.offset :].encode()[:1500].decode("utf-8", errors="ignore")
                )
                end = job.offset + len(fragment)
                locations = [
                    location
                    for start, stop, location in document.locations
                    if start < end and stop > job.offset
                ]
                evidence = json.dumps(
                    {
                        "source": item["source"],
                        "id": item["id"],
                        "version": item["version"],
                        "location": locations,
                        "start": job.offset,
                        "end": end,
                        "text": fragment,
                    },
                    ensure_ascii=False,
                )
                lease = uuid4()
                job.lease, job.lease_until = lease, now + timedelta(minutes=2)
                return DocumentStep(
                    run.id,
                    run.user_id,
                    lease,
                    "reading",
                    job.question,
                    evidence,
                    end,
                    len(fragment),
                )
            job.phase = "combining"
            final = len(job.notes) <= 2
            evidence = json.dumps(
                {
                    "notes": job.notes if final else job.notes[:2],
                    "source_count": len(job.manifest),
                    "empty_sources": sum(item["characters"] == 0 for item in job.manifest),
                    "coverage": "all_available_extracted_text" if final else "intermediate",
                    "warning": "No OCR; lossy summaries; exhaustive findings are not guaranteed.",
                },
                ensure_ascii=False,
            )
            lease = uuid4()
            job.lease, job.lease_until = lease, now + timedelta(minutes=2)
            return DocumentStep(
                run.id,
                run.user_id,
                lease,
                "final" if final else "combining",
                job.question,
                evidence,
            )

    def check(self, step: DocumentStep) -> None:
        with self.sessions.begin() as database:
            if self.current(database, step.run_id, lease=step.lease) is None:
                raise AiConflict("Document processing is no longer current.")

    def complete(self, step: DocumentStep, answer: str) -> bool:
        with self.sessions.begin() as database:
            current = self.current(database, step.run_id, lease=step.lease)
            if current is None:
                return False
            job, run, repository = current
            if step.phase == "reading":
                job.notes = [*job.notes, answer]
                job.processed_characters += step.characters
                job.offset = step.next_offset
            elif step.phase == "combining":
                job.notes = [*job.notes[2:], answer]
            else:
                references = tuple(
                    SourceReference(
                        source=item["source"],
                        id=item["id"],
                        version=item["version"],
                        title=item["title"],
                        locator="full-extracted-text",
                    )
                    for item in job.manifest[:64]
                )
                conversation = self.service.conversation(
                    repository, run.user_id, job.conversation_id
                )
                answer_id = uuid4()
                repository.append_message(
                    Message(
                        id=answer_id,
                        user_id=run.user_id,
                        conversation_id=job.conversation_id,
                        sequence=conversation.next_sequence,
                        role="assistant",
                        content=answer,
                        created_at=self.now(),
                        sources=references,
                    )
                )
                job.answer_message_id = answer_id
                repository.save_run(run.transition("completed", self.now()), "running")
                job.notes, job.phase = [], "completed"
            job.steps += 1
            job.failures = 0
            job.lease, job.lease_until = None, None
            return step.phase != "final"

    def fail(self, step: DocumentStep, error: Exception) -> None:
        with self.sessions.begin() as database:
            current = self.current(database, step.run_id, lease=step.lease)
            if current is None:
                return
            job, run, repository = current
            job.lease = None
            if isinstance(error, ConnectionLimited):
                job.lease_until = self.now() + timedelta(seconds=error.retry_after)
                return
            job.failures += 1
            job.lease_until = self.now() + timedelta(seconds=2**job.failures)
            if job.failures >= 3:
                job.phase, job.error, job.notes = "failed", "processing_failed", []
                stop_run(repository, run, self.now(), status="failed", error="unavailable")

    def progress(self, user_id: UUID, run_id: UUID) -> dict | None:
        self.service.get_run(user_id, run_id)
        with self.sessions() as database:
            job = database.scalar(
                select(DocumentJobModel).where(
                    DocumentJobModel.run_id == run_id, DocumentJobModel.user_id == user_id
                )
            )
            if job is None:
                return None
            return {
                "phase": job.phase,
                "processed_characters": job.processed_characters,
                "total_characters": job.total_characters,
                "steps": job.steps,
                "error": job.error,
            }
