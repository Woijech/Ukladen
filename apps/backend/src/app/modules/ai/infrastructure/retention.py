from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ai.application.recovery import stop_run
from app.modules.ai.domain.state import TERMINAL_RUN_STATUSES
from app.modules.ai.infrastructure.orm import (
    ConversationModel,
    ProviderAttemptModel,
    RunModel,
    RunReceiptModel,
    ToolExecutionModel,
)
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.users.infrastructure.orm import UserModel


def lock_owner(database: Session, user_id: UUID) -> bool:
    return (
        database.scalar(
            select(UserModel.id).where(UserModel.id == user_id).with_for_update(skip_locked=True)
        )
        is not None
    )


def purge_expired(sessions: sessionmaker[Session], *, now: datetime | None = None) -> None:
    """Delete bounded owned batches; the caller selects only a migrated AI database."""
    instant = now or datetime.now(UTC)
    cutoff = instant - timedelta(days=30)
    activity = func.coalesce(ConversationModel.last_user_message_at, ConversationModel.created_at)
    with sessions() as database:
        conversations = list(
            database.execute(
                select(ConversationModel.user_id, ConversationModel.id)
                .where(activity <= cutoff)
                .order_by(activity, ConversationModel.id)
                .limit(100)
            )
        )
    for user_id, conversation_id in conversations:
        with sessions.begin() as database:
            if not lock_owner(database, user_id):
                continue
            repository = SqlAlchemyAiRepository(database)
            conversation = repository.get_conversation(user_id, conversation_id)
            if (
                conversation is None
                or (conversation.last_user_message_at or conversation.created_at) > cutoff
            ):
                continue
            run = repository.active_run(user_id, conversation_id)
            if run is not None:
                stop_run(repository, run, instant, status="cancelled", error="cancelled")
            repository.delete_conversation(user_id, conversation_id)

    old_attempt = (
        select(ProviderAttemptModel.id)
        .where(
            ProviderAttemptModel.run_id == RunModel.id,
            func.coalesce(ProviderAttemptModel.finished_at, ProviderAttemptModel.started_at)
            <= cutoff,
        )
        .exists()
    )
    old_tool = (
        select(ToolExecutionModel.id)
        .where(
            ToolExecutionModel.run_id == RunModel.id,
            func.coalesce(ToolExecutionModel.finished_at, ToolExecutionModel.started_at) <= cutoff,
        )
        .exists()
    )
    with sessions() as database:
        runs = list(
            database.execute(
                select(RunModel.user_id, RunModel.id)
                .where(
                    RunModel.status.in_(TERMINAL_RUN_STATUSES),
                    (RunModel.finished_at <= cutoff) | old_attempt | old_tool,
                )
                .order_by(RunModel.finished_at, RunModel.id)
                .limit(100)
            )
        )
    for user_id, run_id in runs:
        with sessions.begin() as database:
            if not lock_owner(database, user_id):
                continue
            repository = SqlAlchemyAiRepository(database)
            run = repository.get_run(user_id, run_id)
            if run is None or run.status not in TERMINAL_RUN_STATUSES:
                continue
            for model in (ProviderAttemptModel, ToolExecutionModel):
                database.execute(
                    delete(model).where(
                        model.user_id == user_id,
                        model.run_id == run_id,
                        func.coalesce(model.finished_at, model.started_at) <= cutoff,
                    )
                )
            if (
                run.finished_at is not None
                and run.finished_at <= cutoff
                and not repository.attempts(user_id, run_id)
                and not repository.tool_executions(user_id, run_id)
            ):
                database.add(
                    RunReceiptModel(
                        run_id=run.id,
                        user_id=user_id,
                        submission_id=run.submission_id,
                        completed=run.status == "completed",
                    )
                )
                database.flush()
                database.execute(
                    delete(RunModel).where(RunModel.user_id == user_id, RunModel.id == run_id)
                )
