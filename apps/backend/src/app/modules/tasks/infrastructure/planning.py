from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.session import Base
from app.modules.calendar.application.work_sessions import TaskDeadline, WorkSessionBusy
from app.modules.tasks.domain.planning import WeeklyWindow, WorkPreferences, WorkSession
from app.modules.tasks.domain.tasks import InvalidTaskInput
from app.modules.tasks.infrastructure.orm import TaskModel


class WorkSessionModel(Base):
    __tablename__ = "task_work_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_id: Mapped[UUID]
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pinned: Mapped[bool] = mapped_column(Boolean, server_default="false")
    cancelled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    version: Mapped[int] = mapped_column(server_default="1")
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "user_id"], ["tasks.id", "tasks.user_id"], ondelete="CASCADE"
        ),
        CheckConstraint(
            "ends_at > starts_at AND ends_at <= starts_at + interval '24 hours'",
            name="ck_work_session_interval",
        ),
        CheckConstraint("version > 0", name="ck_work_session_version"),
        Index("ix_work_sessions_owner_time", "user_id", "starts_at", "ends_at"),
    )


class WorkPreferencesModel(Base):
    __tablename__ = "task_work_preferences"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int]
    session_minutes: Mapped[int]
    break_minutes: Mapped[int]
    windows: Mapped[list[dict[str, int]]] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_work_preferences_version"),
        CheckConstraint(
            "session_minutes BETWEEN 15 AND 240 AND break_minutes BETWEEN 0 AND 120",
            name="ck_work_preferences_lengths",
        ),
    )


def session_entity(row: WorkSessionModel) -> WorkSession:
    return WorkSession(**{key: getattr(row, key) for key in WorkSession.__dataclass_fields__})


class SqlAlchemyPlanning:
    def __init__(self, database: Session):
        self.database = database

    def preferences(self, user_id: UUID) -> WorkPreferences:
        row = self.database.get(WorkPreferencesModel, user_id, populate_existing=True)
        return (
            WorkPreferences(
                row.version,
                tuple(WeeklyWindow(**item) for item in row.windows),
                row.session_minutes,
                row.break_minutes,
            )
            if row
            else WorkPreferences()
        )

    def save_preferences(self, user_id: UUID, preferences: WorkPreferences) -> None:
        row = self.database.get(WorkPreferencesModel, user_id)
        values = asdict(preferences)
        values["windows"] = [asdict(item) for item in preferences.windows]
        if row is None:
            self.database.add(WorkPreferencesModel(user_id=user_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        self.database.flush()

    def sessions(self, user_id: UUID, starts_at: datetime, ends_at: datetime) -> list[WorkSession]:
        return [
            session_entity(row)
            for row in self.database.scalars(
                select(WorkSessionModel)
                .where(
                    WorkSessionModel.user_id == user_id,
                    WorkSessionModel.starts_at < ends_at,
                    WorkSessionModel.ends_at > starts_at,
                )
                .order_by(WorkSessionModel.starts_at, WorkSessionModel.id)
                .execution_options(populate_existing=True)
            )
        ]

    def session(self, user_id: UUID, session_id: UUID) -> WorkSession | None:
        row = self.database.scalar(
            select(WorkSessionModel)
            .where(WorkSessionModel.user_id == user_id, WorkSessionModel.id == session_id)
            .execution_options(populate_existing=True)
        )
        return session_entity(row) if row else None

    def put_session(self, session: WorkSession) -> None:
        row = self.database.get(WorkSessionModel, session.id)
        if row is None:
            self.database.add(WorkSessionModel(**asdict(session)))
        else:
            for key, value in asdict(session).items():
                setattr(row, key, value)
        self.database.flush()

    def busy(self, user_id: UUID, starts_at: datetime, ends_at: datetime) -> list[WorkSessionBusy]:
        rows = self.database.execute(
            select(WorkSessionModel, TaskModel.title)
            .join(TaskModel, TaskModel.id == WorkSessionModel.task_id)
            .where(
                WorkSessionModel.user_id == user_id,
                WorkSessionModel.cancelled.is_(False),
                WorkSessionModel.starts_at < ends_at,
                WorkSessionModel.ends_at > starts_at,
            )
            .order_by(WorkSessionModel.starts_at, WorkSessionModel.id)
        )
        return [
            WorkSessionBusy(
                f"task_session:{row.id}",
                row.id,
                title,
                row.starts_at,
                row.ends_at,
                row.version,
                task_id=row.task_id,
                pinned=row.pinned,
            )
            for row, title in rows
        ]

    def deadlines(
        self, user_id: UUID, starts_at: datetime, ends_at: datetime
    ) -> list[TaskDeadline]:
        rows = list(
            self.database.scalars(
                select(TaskModel)
                .where(
                    TaskModel.user_id == user_id,
                    TaskModel.trashed_at.is_(None),
                    TaskModel.status.in_(("todo", "in_progress")),
                    TaskModel.deadline_at >= starts_at,
                    TaskModel.deadline_at < ends_at,
                )
                .order_by(TaskModel.deadline_at, TaskModel.id)
                .limit(10001)
            )
        )
        if len(rows) > 10000:
            raise InvalidTaskInput("Too many calendar task dates; narrow the interval.")
        return [
            TaskDeadline(row.id, row.title, row.deadline_at, row.version)
            for row in rows
            if row.deadline_at is not None
        ]

    def lock_schedule(self, user_id: UUID) -> None:
        from app.modules.academics.infrastructure.orm import AcademicProfileModel
        from app.modules.schedule.infrastructure.orm import ScheduleSourceModel

        list(
            self.database.scalars(
                select(ScheduleSourceModel.group_id)
                .where(
                    ScheduleSourceModel.group_id.in_(
                        select(AcademicProfileModel.group_id).where(
                            AcademicProfileModel.user_id == user_id
                        )
                    )
                )
                .order_by(ScheduleSourceModel.group_id)
                .with_for_update(read=True)
            )
        )
