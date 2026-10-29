"""Owned diagnostics use normal AI journals; capture is limited to opted-in chats."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ai.application.diagnostics import DiagnosticReview, capture
from app.modules.ai.domain.state import AiConflict, AiNotFound, Run, RunStatus
from app.modules.ai.infrastructure.diagnostic_models import DiagnosticChatModel, DiagnosticRunModel
from app.modules.ai.infrastructure.orm import ConversationModel, RunModel
from app.modules.ai.infrastructure.retention import lock_owner
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


class SqlAlchemyDiagnostics:
    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions

    def enable(self, user_id: UUID, conversation_id: UUID) -> None:
        with self.sessions.begin() as database:
            if not SqlAlchemyUserAuthentication(database).lock_active(user_id):
                raise AiNotFound()
            chat = database.get(ConversationModel, conversation_id)
            if chat is None or chat.user_id != user_id:
                raise AiNotFound()
            database.add(DiagnosticChatModel(user_id=user_id, conversation_id=conversation_id))

    def list(
        self, user_id: UUID, status: RunStatus | None, days: int, limit: int, offset: int
    ) -> dict:
        with self.sessions() as database:
            query = select(RunModel).where(
                RunModel.user_id == user_id,
                RunModel.created_at > datetime.now(UTC) - timedelta(days=days),
            )
            if status:
                query = query.where(RunModel.status == status)
            rows = list(
                database.scalars(
                    query.order_by(RunModel.created_at.desc(), RunModel.id.desc())
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            items = []
            for row in rows[:limit]:
                trace = database.get(DiagnosticRunModel, row.id)
                if trace and trace.created_at <= datetime.now(UTC) - timedelta(days=7):
                    trace = None
                items.append(
                    {
                        "id": row.id,
                        "conversation_id": row.conversation_id,
                        "provider": row.provider,
                        "model": row.model,
                        "status": row.status,
                        "created_at": row.created_at,
                        "finished_at": row.finished_at,
                        "credential_source": "demo"
                        if row.provider == "fake"
                        else "personal"
                        if row.connection_id
                        else "operator",
                        "captured": bool(
                            trace
                            and trace.events
                            and trace.created_at > datetime.now(UTC) - timedelta(days=7)
                        ),
                        "verdict": trace.verdict if trace else "unreviewed",
                    }
                )
            return {"items": items, "has_more": len(rows) > limit}

    def read(self, user_id: UUID, run_id: UUID) -> dict:
        with self.sessions() as database:
            run = database.get(RunModel, run_id)
            if (
                run is None
                or run.user_id != user_id
                or (run.finished_at or run.created_at) <= datetime.now(UTC) - timedelta(days=30)
            ):
                raise AiNotFound()
            row = database.get(DiagnosticRunModel, run_id)
            if row is None or row.created_at <= datetime.now(UTC) - timedelta(days=7):
                return {
                    "events": [],
                    "captured": False,
                    "truncated": False,
                    "verdict": "unreviewed",
                    "note": "",
                }
            return {
                "events": row.events,
                "captured": bool(row.events),
                "truncated": row.truncated,
                "verdict": row.verdict,
                "note": row.note,
            }

    def review(self, user_id: UUID, run_id: UUID, value: DiagnosticReview) -> None:
        with self.sessions.begin() as database:
            if not SqlAlchemyUserAuthentication(database).lock_active(user_id):
                raise AiNotFound()
            run = database.get(RunModel, run_id)
            if (
                run is None
                or run.user_id != user_id
                or run.conversation_id is None
                or (run.finished_at or run.created_at) <= datetime.now(UTC) - timedelta(days=7)
            ):
                raise AiNotFound()
            row = database.get(DiagnosticRunModel, run_id)
            if row is None:
                row = DiagnosticRunModel(
                    run_id=run_id,
                    conversation_id=run.conversation_id,
                    user_id=user_id,
                    created_at=run.created_at,
                    events=[],
                    truncated=False,
                )
                database.add(row)
            if row.created_at <= datetime.now(UTC) - timedelta(days=7):
                raise AiNotFound()
            row.verdict, row.note = value.verdict, value.note

    def clear(self, user_id: UUID, run_id: UUID) -> None:
        with self.sessions.begin() as database:
            if not SqlAlchemyUserAuthentication(database).lock_active(user_id):
                raise AiNotFound()
            run = database.get(RunModel, run_id)
            if run is None or run.user_id != user_id:
                raise AiNotFound()
            if run.status in ("queued", "running", "interrupted"):
                raise AiConflict("Stop the run before clearing capture.")
            database.execute(
                delete(DiagnosticRunModel).where(
                    DiagnosticRunModel.user_id == user_id, DiagnosticRunModel.run_id == run_id
                )
            )

    @contextmanager
    def capturing(self, run: Run, allowed: bool):
        enabled = False
        if allowed:
            with self.sessions() as database:
                chat = database.get(DiagnosticChatModel, run.conversation_id)
                enabled = chat is not None and chat.user_id == run.user_id
        token = (
            capture.set(lambda kind, payload: self.append(run, kind, payload))
            if enabled
            else capture.set(None)
        )
        try:
            yield
        finally:
            capture.reset(token)

    def append(self, run: Run, kind: str, payload: object) -> None:
        with self.sessions.begin() as database:
            if not SqlAlchemyUserAuthentication(database).lock_active(run.user_id):
                return
            current = database.get(RunModel, run.id)
            if (
                current is None
                or current.status != "running"
                or current.conversation_id is None
                or current.created_at <= datetime.now(UTC) - timedelta(days=7)
            ):
                return
            row = database.get(DiagnosticRunModel, run.id)
            if row is None:
                row = DiagnosticRunModel(
                    run_id=run.id,
                    conversation_id=current.conversation_id,
                    user_id=run.user_id,
                    created_at=run.created_at,
                    events=[],
                    truncated=False,
                    verdict="unreviewed",
                    note="",
                )
                database.add(row)
            event = {"kind": kind, "at": datetime.now(UTC).isoformat(), "payload": payload}
            events = [*row.events, event]
            if len(events) > 64 or len(json.dumps(events, ensure_ascii=False).encode()) > 240000:
                row.truncated = True
            else:
                row.events = events


def purge_diagnostics(sessions: sessionmaker[Session], now: datetime) -> None:
    with sessions.begin() as database:
        rows = database.execute(
            select(DiagnosticRunModel.user_id, DiagnosticRunModel.run_id)
            .where(DiagnosticRunModel.created_at <= now - timedelta(days=7))
            .limit(100)
        ).all()
        for user_id, run_id in rows:
            if lock_owner(database, user_id):
                database.execute(
                    delete(DiagnosticRunModel).where(
                        DiagnosticRunModel.run_id == run_id, DiagnosticRunModel.user_id == user_id
                    )
                )
