from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ai.application.recovery import RUN_TIMEOUT, stop_run
from app.modules.ai.infrastructure.document_models import DocumentJobModel
from app.modules.ai.infrastructure.orm import RunModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.users.infrastructure.orm import UserModel


def reconcile_runs(sessions: sessionmaker[Session], *, now: datetime | None = None) -> int:
    """Bounded system maintenance; never dispatch a model or replay a checkpoint."""
    instant = now or datetime.now(UTC)
    cutoff = instant - RUN_TIMEOUT
    with sessions() as database:
        candidates = list(
            database.execute(
                select(RunModel.user_id, RunModel.id)
                .where(
                    RunModel.status.in_(("queued", "running")),
                    RunModel.created_at <= cutoff,
                    ~select(DocumentJobModel.run_id)
                    .where(DocumentJobModel.run_id == RunModel.id)
                    .exists(),
                )
                .order_by(RunModel.created_at, RunModel.id)
                .limit(100)
            )
        )
    count = 0
    for user_id, run_id in candidates:
        with sessions.begin() as database:
            # Match ordinary owner-first serialization, including disabled owners.
            owner = database.scalar(
                select(UserModel.id)
                .where(UserModel.id == user_id)
                .with_for_update(skip_locked=True)
            )
            if owner is None:
                continue
            repository = SqlAlchemyAiRepository(database)
            run = repository.get_run(user_id, run_id)
            if run is None or run.status not in {"queued", "running"} or run.created_at > cutoff:
                continue
            stop_run(repository, run, instant, status="failed", error="interrupted")
            count += 1
    return count
