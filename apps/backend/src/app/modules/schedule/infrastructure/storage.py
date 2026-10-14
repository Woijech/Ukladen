from collections import defaultdict
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.modules.academics.domain.profile import AcademicProfileConflict
from app.modules.schedule.application.provider import Schedule
from app.modules.schedule.application.storage import ScheduleState, SyncState
from app.modules.schedule.domain.events import OfficialEvent
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel, ScheduleSourceModel


def event_entity(row: OfficialScheduleEventModel) -> OfficialEvent:
    return OfficialEvent(
        id=row.id,
        group_id=row.group_id,
        kind=cast(Literal["lesson", "exam", "announcement"], row.kind),
        subgroup=row.subgroup,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        subject=row.subject,
        subject_full_name=row.subject_full_name,
        lesson_type=row.lesson_type,
        note=row.note,
        rooms=tuple(row.rooms),
        teacher_ids=tuple(row.teacher_ids),
        teacher_names=tuple(row.teacher_names),
        active=row.active,
    )


class SqlAlchemyScheduleStore:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        interval_seconds: int = 3600,
        *,
        read_session: Session | None = None,
    ) -> None:
        self.sessions = sessions
        self.interval = timedelta(seconds=interval_seconds)
        self.read_session = read_session

    def _reading(self) -> AbstractContextManager[Session]:
        """Calendar reads join its caller-owned snapshot; standalone reads stay unchanged."""
        return (
            nullcontext(self.read_session)
            if self.read_session is not None
            else self.sessions.begin()
        )

    def claim(
        self, group_id: int, group_number: str, now: datetime, *, force: bool = False
    ) -> UUID | None:
        with self.sessions.begin() as database:
            database.execute(
                insert(ScheduleSourceModel)
                .values(group_id=group_id, group_number=group_number, status="syncing")
                .on_conflict_do_nothing(index_elements=[ScheduleSourceModel.group_id])
            )
            row = database.scalar(
                select(ScheduleSourceModel)
                .where(ScheduleSourceModel.group_id == group_id)
                .with_for_update()
            )
            assert row is not None
            if row.group_number != group_number:
                raise AcademicProfileConflict()
            if row.lease_until is not None and row.lease_until > now:
                return None
            expired = row.lease_until is not None and row.lease_until <= now
            wait = timedelta(seconds=60) if force else self.interval
            if not expired and row.last_attempt_at is not None and row.last_attempt_at + wait > now:
                return None
            token = uuid4()
            row.sync_token, row.lease_until = token, now + timedelta(minutes=2)
            row.last_attempt_at, row.status, row.error_code = now, "syncing", None
            return token

    def apply(
        self,
        group_id: int,
        token: UUID,
        snapshot: Schedule | None,
        events: list[OfficialEvent],
        now: datetime,
    ) -> bool:
        with self.sessions.begin() as database:
            source = self._owned(database, group_id, token, now)
            if source is None:
                return False
            rows = list(
                database.scalars(
                    select(OfficialScheduleEventModel)
                    .where(OfficialScheduleEventModel.group_id == group_id)
                    .order_by(
                        OfficialScheduleEventModel.active.desc(), OfficialScheduleEventModel.id
                    )
                )
            )
            exact: dict[tuple[object, ...], list[OfficialScheduleEventModel]] = defaultdict(list)
            logical: dict[tuple[object, ...], list[OfficialScheduleEventModel]] = defaultdict(list)
            incoming: dict[tuple[object, ...], int] = defaultdict(int)
            for row in rows:
                entity = event_entity(row)
                exact[entity.content_key].append(row)
                if row.active:
                    logical[entity.identity_key].append(row)
                row.active = False
            for item in events:
                if item.group_id != group_id:
                    raise AcademicProfileConflict()
                incoming[item.identity_key] += 1
            used: set[UUID] = set()
            for item in events:
                candidates = [row for row in exact[item.content_key] if row.id not in used]
                target = candidates[0] if candidates else None
                same_lesson = logical[item.identity_key]
                if target is None and len(same_lesson) == 1 and incoming[item.identity_key] == 1:
                    if same_lesson[0].id not in used:
                        target = same_lesson[0]
                values = asdict(item)
                values.pop("id")
                values["active"] = True
                if target is None:
                    target = OfficialScheduleEventModel(id=item.id, **values)
                    database.add(target)
                else:
                    for key, value in values.items():
                        setattr(target, key, value)
                used.add(target.id)
            source.snapshot = snapshot.model_dump(mode="json") if snapshot else None
            source.status = "ready" if snapshot is not None else "unpublished"
            source.last_success_at, source.error_code = now, None
            source.sync_token, source.lease_until = None, None
            return True

    def fail(self, group_id: int, token: UUID, code: str, now: datetime) -> None:
        with self.sessions.begin() as database:
            source = self._owned(database, group_id, token, now)
            if source is not None:
                source.status = (
                    "unsupported"
                    if code == "unsupported_schedule" or code.startswith("unsupported_")
                    else "error"
                )
                source.error_code = code
                source.sync_token, source.lease_until = None, None

    @staticmethod
    def _owned(
        database: Session, group_id: int, token: UUID, now: datetime
    ) -> ScheduleSourceModel | None:
        source = database.scalar(
            select(ScheduleSourceModel)
            .where(ScheduleSourceModel.group_id == group_id)
            .with_for_update()
        )
        if source is None or source.sync_token != token:
            return None
        if source.lease_until is None or source.lease_until <= now:
            return None
        return source

    def state(self, group_id: int, group_number: str) -> ScheduleState:
        with self._reading() as database:
            row = database.get(ScheduleSourceModel, group_id)
            if row is None:
                return ScheduleState(group_id, group_number)
            if row.group_number != group_number:
                raise AcademicProfileConflict()
            return ScheduleState(
                row.group_id,
                row.group_number,
                cast(SyncState, row.status),
                row.last_attempt_at,
                row.last_success_at,
                row.error_code,
            )

    def group_id(self, group_number: str) -> int | None:
        with self._reading() as database:
            return database.scalar(
                select(ScheduleSourceModel.group_id).where(
                    ScheduleSourceModel.group_number == group_number
                )
            )

    def events(
        self, group_id: int, starts_at: datetime, ends_at: datetime, subgroup: int | None
    ) -> list[OfficialEvent]:
        query = (
            select(OfficialScheduleEventModel)
            .where(
                OfficialScheduleEventModel.group_id == group_id,
                OfficialScheduleEventModel.active,
                OfficialScheduleEventModel.starts_at < ends_at,
                OfficialScheduleEventModel.ends_at > starts_at,
            )
            .order_by(OfficialScheduleEventModel.starts_at, OfficialScheduleEventModel.id)
        )
        if subgroup is not None:
            query = query.where(OfficialScheduleEventModel.subgroup.in_([0, subgroup]))
        with self._reading() as database:
            return [event_entity(row) for row in database.scalars(query)]

    def read(
        self,
        group_id: int,
        group_number: str,
        starts_at: datetime,
        ends_at: datetime,
        subgroup: int | None,
        event_ids: tuple[UUID, ...] = (),
    ) -> tuple[ScheduleState, list[OfficialEvent]]:
        conditions = [
            OfficialScheduleEventModel.group_id == ScheduleSourceModel.group_id,
            OfficialScheduleEventModel.active,
            or_(
                and_(
                    OfficialScheduleEventModel.starts_at < ends_at,
                    OfficialScheduleEventModel.ends_at > starts_at,
                ),
                OfficialScheduleEventModel.id.in_(event_ids),
            ),
        ]
        if subgroup is not None:
            conditions.append(OfficialScheduleEventModel.subgroup.in_([0, subgroup]))
        with self._reading() as database:
            rows = database.execute(
                select(ScheduleSourceModel, OfficialScheduleEventModel)
                .outerjoin(OfficialScheduleEventModel, and_(*conditions))
                .where(ScheduleSourceModel.group_id == group_id)
                .order_by(OfficialScheduleEventModel.starts_at, OfficialScheduleEventModel.id)
            ).all()
            if not rows:
                return ScheduleState(group_id, group_number), []
            source = rows[0][0]
            if source.group_number != group_number:
                raise AcademicProfileConflict()
            state = ScheduleState(
                source.group_id,
                source.group_number,
                cast(SyncState, source.status),
                source.last_attempt_at,
                source.last_success_at,
                source.error_code,
            )
            return state, [event_entity(row[1]) for row in rows if row[1] is not None]

    def event(self, event_id: UUID) -> OfficialEvent | None:
        with self._reading() as database:
            row = database.get(OfficialScheduleEventModel, event_id)
            return event_entity(row) if row else None

    def by_ids(self, event_ids: tuple[UUID, ...]) -> list[OfficialEvent]:
        if not event_ids:
            return []
        with self._reading() as database:
            return [
                event_entity(row)
                for row in database.scalars(
                    select(OfficialScheduleEventModel).where(
                        OfficialScheduleEventModel.id.in_(event_ids)
                    )
                )
            ]
