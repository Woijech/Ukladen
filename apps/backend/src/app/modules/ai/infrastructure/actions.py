from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ai.application.actions import (
    ActionBatch,
    ActionContext,
    ActionOutcome,
    Proposal,
    ReminderCreate,
)
from app.modules.ai.application.source_queries import (
    CalendarRead,
    DatabaseRead,
    MaterialRead,
    PageRead,
    RecordRead,
)
from app.modules.ai.domain.state import AiConflict, AiPersistenceUnavailable
from app.modules.ai.infrastructure.action_models import ActionProposalModel, ActionReceiptModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.ai.infrastructure.task_origins import SqlAlchemyTaskOrigins
from app.modules.calendar.application.availability import CalendarAvailabilityService
from app.modules.relations.application.task_links import TaskRelationService
from app.modules.relations.infrastructure.task_links import SqlAlchemyTaskPageLinks
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel
from app.modules.search.domain.evidence import SourceReference
from app.modules.tasks.application.dependencies import TaskDependencyService
from app.modules.tasks.application.planning import PlanningService
from app.modules.tasks.application.plans import PlanService
from app.modules.tasks.application.service import TaskService
from app.modules.tasks.infrastructure.dependencies import SqlAlchemyTaskDependencies
from app.modules.tasks.infrastructure.planning import SqlAlchemyPlanning
from app.modules.tasks.infrastructure.plans import SqlAlchemyPlans
from app.modules.tasks.infrastructure.repository import SqlAlchemyTaskRepository
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import (
    SqlAlchemyProfileRepository,
    SqlAlchemyUserAuthentication,
)


class SqlAlchemyActions:
    def __init__(self, database: Session):
        self.database = database

    def get(self, user_id: UUID, proposal_id: UUID) -> Proposal | None:
        row = self.database.scalar(
            select(ActionProposalModel).where(
                ActionProposalModel.user_id == user_id, ActionProposalModel.id == proposal_id
            )
        )
        if row is None:
            return None
        receipt = self.database.scalar(
            select(ActionReceiptModel).where(
                ActionReceiptModel.proposal_id == proposal_id, ActionReceiptModel.user_id == user_id
            )
        )
        return Proposal.model_validate(
            dict(
                id=row.id,
                run_id=row.run_id,
                conversation_id=row.conversation_id,
                interrupt_id=row.interrupt_id,
                digest=row.digest,
                created_at=row.created_at,
                expires_at=row.expires_at,
                status=receipt.status if receipt else "pending",
                outcomes=tuple(ActionOutcome.model_validate(item) for item in receipt.outcomes)
                if receipt
                else (),
                **row.payload,
            )
        )

    def list(self, user_id: UUID, conversation_id: UUID, limit: int, offset: int) -> list[Proposal]:
        identifiers = self.database.scalars(
            select(ActionProposalModel.id)
            .where(
                ActionProposalModel.user_id == user_id,
                ActionProposalModel.conversation_id == conversation_id,
            )
            .order_by(ActionProposalModel.created_at.desc(), ActionProposalModel.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            proposal for identifier in identifiers if (proposal := self.get(user_id, identifier))
        ]

    def put(self, user_id: UUID, proposal: Proposal) -> None:
        if self.database.get(ActionProposalModel, proposal.id) is None:
            if self.database.get(ActionReceiptModel, proposal.id) is not None:
                raise AiConflict("Proposal identifier is retired.")
            payload = proposal.model_dump(
                mode="json", include={"batch", "effects", "sources", "timezone"}
            )
            # Omitted patch fields must remain omitted after a durable reload.
            payload["batch"] = proposal.batch.model_dump(mode="json", exclude_unset=True)
            self.database.add(
                ActionProposalModel(
                    id=proposal.id,
                    user_id=user_id,
                    run_id=proposal.run_id,
                    conversation_id=proposal.conversation_id,
                    interrupt_id=proposal.interrupt_id,
                    digest=proposal.digest,
                    created_at=proposal.created_at,
                    expires_at=proposal.expires_at,
                    payload=payload,
                )
            )
        if (
            proposal.status != "pending"
            and self.database.get(ActionReceiptModel, proposal.id) is None
        ):
            self.database.add(
                ActionReceiptModel(
                    proposal_id=proposal.id,
                    user_id=user_id,
                    status=proposal.status,
                    outcomes=[item.model_dump(mode="json") for item in proposal.outcomes],
                    finished_at=datetime.now(UTC),
                )
            )
        self.database.flush()

    def supersede(self, user_id: UUID, conversation_id: UUID) -> None:
        identifiers = list(
            self.database.scalars(
                select(ActionProposalModel.id).where(
                    ActionProposalModel.user_id == user_id,
                    ActionProposalModel.conversation_id == conversation_id,
                    ~select(ActionReceiptModel.proposal_id)
                    .where(ActionReceiptModel.proposal_id == ActionProposalModel.id)
                    .exists(),
                )
            )
        )
        for identifier in identifiers:
            proposal = self.get(user_id, identifier)
            if proposal is not None:
                self.put(user_id, proposal.model_copy(update={"status": "superseded"}))


class SqlAlchemyActionTransactions:
    def __init__(self, sources: SqlAlchemySourceReader):
        self.sources = sources
        self.sessions: sessionmaker[Session] = sources.sessions

    @contextmanager
    def __call__(self, user_id: UUID) -> Iterator[ActionContext]:
        try:
            with self.sessions.begin() as database:
                database.execute(text("SET LOCAL statement_timeout = '10s'"))
                users = SqlAlchemyUserAuthentication(database)
                if not users.lock_active(user_id):
                    raise ProfileUnavailable()
                workspace = self.sources.service(database)
                calendar = workspace.calendar.calendar
                profile = SqlAlchemyProfileRepository(database).get_active(user_id)
                if profile is None:
                    raise ProfileUnavailable()

                def lock_events(batch: ActionBatch) -> None:
                    identifiers = sorted(
                        {
                            action.event_id
                            for action in batch.actions
                            if isinstance(action, ReminderCreate)
                            and action.source == "official"
                            and action.event_id is not None
                        }
                    )
                    if identifiers:
                        list(
                            database.scalars(
                                select(OfficialScheduleEventModel.id)
                                .where(OfficialScheduleEventModel.id.in_(identifiers))
                                .order_by(OfficialScheduleEventModel.id)
                                .with_for_update(read=True)
                            )
                        )

                def validate_sources(sources: tuple[SourceReference, ...]) -> None:
                    official = sorted(
                        {UUID(item.id) for item in sources if item.source == "official"}
                    )
                    if official:
                        list(
                            database.scalars(
                                select(OfficialScheduleEventModel.id)
                                .where(OfficialScheduleEventModel.id.in_(official))
                                .order_by(OfficialScheduleEventModel.id)
                                .with_for_update(read=True)
                            )
                        )
                    for source in sources:
                        if source.source == "web":
                            # Web citations are snapshots; exact proposed content is reviewed.
                            continue
                        if source.source == "task":
                            task = TaskService(SqlAlchemyTaskRepository(database), users).get(
                                user_id, UUID(source.id)
                            )
                            if (
                                task.trashed_at is not None
                                or task.version != source.version
                                or task.title != source.title
                            ):
                                raise AiConflict("Task source changed.")
                            continue
                        if source.source == "personal":
                            current = calendar.get_personal_event(user_id, UUID(source.id))
                            valid = (
                                current.version == source.version and current.title == source.title
                            )
                        else:
                            if source.source == "page":
                                query = PageRead(page_id=UUID(source.id), limit=1)
                            elif source.source == "material":
                                query = MaterialRead(material_id=UUID(source.id), limit=1)
                            elif source.source == "database":
                                query = DatabaseRead(database_id=UUID(source.id), limit=1)
                            elif source.source == "database_record" and source.parent_id:
                                query = RecordRead(
                                    database_id=UUID(source.parent_id),
                                    record_id=UUID(source.id),
                                    limit=1,
                                )
                            elif source.source in (
                                "official",
                                "record_date",
                            ) and source.locator.startswith("dates:"):
                                _, start, end = source.locator.split(":")
                                query = CalendarRead(
                                    date_from=date.fromisoformat(start),
                                    date_to=date.fromisoformat(end),
                                    include_hidden=True,
                                    limit=20,
                                )
                            else:
                                raise AiConflict("Source cannot be revalidated.")
                            if (
                                source.source in ("official", "record_date")
                                and source.fingerprint is None
                            ):
                                raise AiConflict(
                                    "Read current source facts before proposing actions."
                                )
                            valid = False
                            while True:
                                result = workspace.read(user_id, query)
                                if result.status != "ok":
                                    break
                                valid = any(
                                    (item.source, item.id, item.version, item.title)
                                    == (source.source, source.id, source.version, source.title)
                                    and (
                                        source.source != "database_record"
                                        or not source.locator.startswith("schema:")
                                        or source.locator == item.locator
                                    )
                                    and (
                                        source.fingerprint is None
                                        or item.fingerprint == source.fingerprint
                                    )
                                    for item in result.sources
                                )
                                if (
                                    valid
                                    or not isinstance(query, CalendarRead)
                                    or result.next_offset is None
                                ):
                                    break
                                query = query.model_copy(update={"offset": result.next_offset})
                            if not valid:
                                raise AiConflict("Source changed; request a new preview.")
                        if not valid:
                            raise AiConflict("Source changed; request a new preview.")

                tasks = TaskService(SqlAlchemyTaskRepository(database), users)
                planning_repository = SqlAlchemyPlanning(database)
                planning = PlanningService(
                    tasks,
                    planning_repository,
                    CalendarAvailabilityService(calendar, planning_repository),
                )
                origins = SqlAlchemyTaskOrigins(
                    database,
                    tasks,
                    TaskRelationService(SqlAlchemyTaskPageLinks(database), workspace.notes, tasks),
                )
                yield ActionContext(
                    SqlAlchemyAiRepository(database),
                    SqlAlchemyActions(database),
                    workspace.notes,
                    calendar,
                    ReminderService(SqlAlchemyReminderRepository(database), users, calendar),
                    profile.timezone,
                    lock_events,
                    validate_sources,
                    tasks,
                    TaskDependencyService(tasks, SqlAlchemyTaskDependencies(database)),
                    PlanService(planning, SqlAlchemyPlans(database)),
                    origins.save,
                )
        except IntegrityError:
            raise AiConflict("Action state changed or a constraint rejected the request.") from None
        except SQLAlchemyError:
            raise AiPersistenceUnavailable("Action storage is unavailable.") from None
