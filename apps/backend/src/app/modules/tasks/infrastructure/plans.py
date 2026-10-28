from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.session import Base
from app.modules.tasks.application.plans import PlanPreview
from app.modules.tasks.domain.planning import WorkSession
from app.modules.tasks.domain.tasks import InvalidTaskInput, TaskSummary
from app.modules.tasks.infrastructure.orm import TaskDependencyModel, TaskModel
from app.modules.tasks.infrastructure.planning import WorkSessionModel, session_entity
from app.modules.tasks.infrastructure.repository import task_summary


class TaskPlanModel(Base):
    __tablename__ = "task_plans"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'applied', 'rejected', 'expired')", name="ck_task_plan_status"
        ),
    )


class SqlAlchemyPlans:
    def __init__(self, database: Session):
        self.database = database

    def facts(
        self, user_id: UUID, now: datetime
    ) -> tuple[list[TaskSummary], list[tuple[UUID, UUID]], list[WorkSession]]:
        tasks = [
            task_summary(row)
            for row in self.database.scalars(
                select(TaskModel)
                .where(TaskModel.user_id == user_id)
                .order_by(TaskModel.id)
                .limit(2001)
                .execution_options(populate_existing=True)
            )
        ]
        sessions = [
            session_entity(row)
            for row in self.database.scalars(
                select(WorkSessionModel)
                .where(
                    WorkSessionModel.user_id == user_id,
                    WorkSessionModel.ends_at > now,
                    WorkSessionModel.cancelled.is_(False),
                )
                .order_by(WorkSessionModel.id)
                .limit(10001)
                .execution_options(populate_existing=True)
            )
        ]
        edges = [
            (row.task_id, row.predecessor_id)
            for row in self.database.scalars(
                select(TaskDependencyModel)
                .where(TaskDependencyModel.user_id == user_id)
                .order_by(TaskDependencyModel.task_id, TaskDependencyModel.predecessor_id)
                .limit(10001)
            )
        ]
        if len(tasks) > 2000 or len(sessions) > 10000 or len(edges) > 10000:
            raise InvalidTaskInput("Planning input exceeds the supported bound.")
        return tasks, edges, sessions

    def get(self, user_id: UUID, plan_id: UUID) -> PlanPreview | None:
        row = self.database.scalar(
            select(TaskPlanModel)
            .where(TaskPlanModel.user_id == user_id, TaskPlanModel.id == plan_id)
            .execution_options(populate_existing=True)
        )
        return PlanPreview.model_validate(row.payload | {"status": row.status}) if row else None

    def put(self, user_id: UUID, preview: PlanPreview) -> None:
        row = self.database.get(TaskPlanModel, preview.id)
        if row is None:
            self.database.add(
                TaskPlanModel(
                    id=preview.id,
                    user_id=user_id,
                    payload=preview.model_dump(mode="json"),
                    status=preview.status,
                    created_at=preview.created_at,
                )
            )
        else:
            row.status = preview.status
        self.database.flush()
