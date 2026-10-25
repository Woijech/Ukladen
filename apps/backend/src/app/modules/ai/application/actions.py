"""Exact owner-confirmed proposals; ordinary services remain the write authority."""

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from app.modules.ai.application.agent import PendingReview
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.domain.state import AiConflict, AiNotFound, Run
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.domain.events import PERSONAL_FIELDS, personal_values
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.blocks import document_value, parse_document
from app.modules.notes.domain.pages import page_title
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.domain.reminders import trigger_time
from app.modules.search.domain.evidence import SourceReference


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class PageCreate(ActionInput):
    operation: Literal["page_create"]
    title: str = Field(min_length=1, max_length=200, strict=True)
    parent_id: UUID | None = None
    document: dict[str, JsonValue]


class PageUpdate(ActionInput):
    operation: Literal["page_update"]
    page_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    document: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def has_changes(self) -> Self:
        if self.title is None and self.document is None:
            raise ValueError("Provide a title or document change.")
        return self


class EventValues(ActionInput):
    title: str = Field(min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: str | None = Field(default=None, max_length=500, strict=True)
    blocks_time: bool = Field(strict=True)

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        if not isinstance(value, datetime) and not (isinstance(value, str) and "T" in value):
            raise ValueError("An explicit offset-aware timestamp is required.")
        return value

    @model_validator(mode="after")
    def valid_event(self) -> Self:
        personal_values({name: getattr(self, name) for name in PERSONAL_FIELDS})
        return self


class EventCreate(EventValues):
    operation: Literal["event_create"]


class EventChanges(ActionInput):
    title: str | None = Field(default=None, min_length=1, max_length=200, strict=True)
    description: str | None = Field(default=None, max_length=10000, strict=True)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=500, strict=True)
    blocks_time: bool | None = Field(default=None, strict=True)

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        return EventValues.explicit_timestamp(value)

    @model_validator(mode="after")
    def valid_changes(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, name) is None
            for name in self.model_fields_set
            if name not in ("description", "location")
        ):
            raise ValueError(
                "Provide explicit non-null changes; only description/location may be cleared."
            )
        return self


class EventUpdate(ActionInput):
    operation: Literal["event_update"]
    event_id: UUID
    expected_version: int = Field(ge=1, strict=True)
    changes: EventChanges


class ReminderCreate(ActionInput):
    operation: Literal["reminder_create"]
    source: Literal["personal", "official"] = "personal"
    event_id: UUID | None = None
    event_action: int | None = Field(default=None, ge=0, le=7, strict=True)
    minutes_before: int = Field(ge=0, le=43200, strict=True)

    @model_validator(mode="after")
    def exact_target(self) -> Self:
        if (self.event_id is None) == (self.event_action is None):
            raise ValueError("Select an event ID or the index of an earlier event action.")
        if self.event_action is not None and self.source != "personal":
            raise ValueError("New events are personal.")
        return self


Operation = Annotated[
    PageCreate | PageUpdate | EventCreate | EventUpdate | ReminderCreate,
    Field(discriminator="operation"),
]


class ActionBatch(ActionInput):
    actions: tuple[Operation, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def valid_batch(self) -> Self:
        targets: set[tuple[str, UUID]] = set()
        for index, action in enumerate(self.actions):
            if isinstance(action, (PageUpdate, EventUpdate)):
                key = (
                    ("page", action.page_id)
                    if isinstance(action, PageUpdate)
                    else ("event", action.event_id)
                )
                if key in targets:
                    raise ValueError("Each existing target may be edited only once per proposal.")
                targets.add(key)
            if isinstance(action, ReminderCreate) and action.event_action is not None:
                if action.event_action >= index or not isinstance(
                    self.actions[action.event_action], (EventCreate, EventUpdate)
                ):
                    raise ValueError("Reminder must reference an earlier event action.")
        edited_events = {
            action.event_id for action in self.actions if isinstance(action, EventUpdate)
        }
        if any(
            isinstance(action, ReminderCreate) and action.event_id in edited_events
            for action in self.actions
        ):
            raise ValueError("Use event_action for reminders on events edited in this batch.")
        if len(self.model_dump_json().encode()) > 16384:
            raise ValueError("Proposal arguments exceed the tool input bound.")
        return self


class ActionEffect(ActionInput):
    operation: str
    target_id: UUID | None = None
    before: dict[str, JsonValue] | None = None
    after: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()


class ActionOutcome(ActionInput):
    operation: str
    target_id: UUID


class Proposal(ActionInput):
    id: UUID
    run_id: UUID
    conversation_id: UUID
    interrupt_id: str
    digest: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    status: Literal["pending", "applied", "rejected", "expired", "conflict", "superseded"]
    batch: ActionBatch
    effects: tuple[ActionEffect, ...]
    sources: tuple[SourceReference, ...] = ()
    timezone: str
    outcomes: tuple[ActionOutcome, ...] = ()


class ProposalDecision(ActionInput):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["approve", "reject"]


class ActionRepository(Protocol):
    def get(self, user_id: UUID, proposal_id: UUID) -> Proposal | None: ...
    def list(
        self, user_id: UUID, conversation_id: UUID, limit: int, offset: int
    ) -> list[Proposal]: ...
    def put(self, user_id: UUID, proposal: Proposal) -> None: ...
    def supersede(self, user_id: UUID, conversation_id: UUID) -> None: ...


@dataclass
class ActionContext:
    ai: AiRepository
    proposals: ActionRepository
    notes: NoteService
    calendar: CalendarService
    reminders: ReminderService
    timezone: str
    lock_events: Callable[[ActionBatch], None]
    validate_sources: Callable[[tuple[SourceReference, ...]], None]


class ActionTransactions(Protocol):
    def __call__(self, user_id: UUID) -> AbstractContextManager[ActionContext]: ...


def json_object(value: object) -> dict[str, JsonValue]:
    return json.loads(
        json.dumps(
            value,
            default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
            ensure_ascii=False,
        )
    )


class ActionService:
    def __init__(
        self,
        transactions: ActionTransactions,
        *,
        connections: ConnectionAccess | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.transactions, self.connections, self.now = transactions, connections, now

    def context(self, unit: ActionContext, user_id: UUID, conversation_id: UUID) -> None:
        conversation = unit.ai.get_conversation(user_id, conversation_id)
        if conversation is None or (
            conversation.last_user_message_at or conversation.created_at
        ) <= self.now() - timedelta(days=30):
            raise AiNotFound()

    def capability(self, unit: ActionContext, user_id: UUID, run: Run) -> None:
        if run.offering_id is not None:
            if self.connections is None:
                raise AiConflict("Action capabilities are unavailable.")
            # No credential read, admission or provider request is needed for confirmation.
            offering = self.connections.configuration.offering(user_id, run.offering_id)
            if not offering.tools or offering.version != run.offering_version:
                raise AiConflict("Action capabilities changed.")
            if run.connection_id is not None:
                connection = unit.ai.get_connection(user_id, run.connection_id)
                if connection is None or connection.disconnected_at is not None:
                    raise AiConflict("Connection is disconnected.")

    def propose(
        self, run: Run, review: PendingReview, sources: tuple[SourceReference, ...] = ()
    ) -> Proposal:
        if len(review.actions) != 1 or review.actions[0].tool_name != "propose_actions":
            raise AiConflict("Only one complete action batch may be reviewed.")
        batch = ActionBatch.model_validate(review.actions[0].arguments)
        with self.transactions(run.user_id) as unit:
            if run.conversation_id is None:
                raise AiNotFound()
            self.context(unit, run.user_id, run.conversation_id)
            current = unit.ai.get_run(run.user_id, run.id)
            if current is None or current.status != "running":
                raise AiConflict("Execution is no longer active.")
            self.capability(unit, run.user_id, current)
            unit.lock_events(batch)
            unit.validate_sources(sources)
            effects = self.preview(unit, run.user_id, batch)
            now = self.now()
            payload = json_object(
                {
                    "batch": batch.model_dump(mode="json"),
                    "effects": [effect.model_dump(mode="json") for effect in effects],
                    "sources": [source.model_dump(mode="json") for source in sources],
                    "timezone": unit.timezone,
                }
            )
            encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
            if len(encoded) > 2 * 1024 * 1024:
                raise ValueError("Preview exceeds the transport bound; narrow the requested edit.")
            proposal = Proposal(
                id=uuid4(),
                run_id=run.id,
                conversation_id=run.conversation_id,
                interrupt_id=review.interrupt_id,
                digest=hashlib.sha256(encoded).hexdigest(),
                created_at=now,
                expires_at=now + timedelta(hours=24),
                status="pending",
                batch=batch,
                effects=effects,
                sources=sources,
                timezone=unit.timezone,
            )
            unit.proposals.supersede(run.user_id, run.conversation_id)
            unit.proposals.put(run.user_id, proposal)
            return proposal

    def list(self, user_id: UUID, conversation_id: UUID, limit: int, offset: int) -> list[Proposal]:
        with self.transactions(user_id) as unit:
            self.context(unit, user_id, conversation_id)
            return [
                self.expiry(item)
                for item in unit.proposals.list(user_id, conversation_id, limit, offset)
            ]

    def expiry(self, proposal: Proposal) -> Proposal:
        return (
            proposal.model_copy(update={"status": "expired"})
            if (proposal.status == "pending" and self.now() >= proposal.expires_at)
            else proposal
        )

    def decide(self, user_id: UUID, proposal_id: UUID, decision: ProposalDecision) -> Proposal:
        with self.transactions(user_id) as unit:
            proposal = unit.proposals.get(user_id, proposal_id)
            if proposal is None:
                raise AiNotFound()
            self.context(unit, user_id, proposal.conversation_id)
            if proposal.digest != decision.digest:
                raise AiConflict("Proposal does not match the reviewed preview.")
            if proposal.status != "pending":
                return proposal
            proposal = self.expiry(proposal)
            if proposal.status == "pending" and decision.decision == "reject":
                proposal = proposal.model_copy(update={"status": "rejected"})
            if proposal.status == "pending":
                run = unit.ai.get_run(user_id, proposal.run_id)
                if run is None or run.status != "completed":
                    raise AiConflict("Proposal execution is unavailable.")
                self.capability(unit, user_id, run)
                unit.lock_events(proposal.batch)
                unit.validate_sources(proposal.sources)
                current = self.preview(unit, user_id, proposal.batch)
                if current != proposal.effects or unit.timezone != proposal.timezone:
                    proposal = proposal.model_copy(update={"status": "conflict"})
                else:
                    outcomes = self.apply(unit, user_id, proposal.batch)
                    proposal = proposal.model_copy(
                        update={"status": "applied", "outcomes": outcomes}
                    )
            unit.proposals.put(user_id, proposal)
            return proposal

    def preview(
        self, unit: ActionContext, user_id: UUID, batch: ActionBatch
    ) -> tuple[ActionEffect, ...]:
        effects: list[ActionEffect] = []
        for action in batch.actions:
            before, target, warnings = None, None, ()
            if isinstance(action, PageCreate):
                after = json_object(
                    {
                        "title": page_title(action.title),
                        "parent_id": action.parent_id,
                        "document": document_value(parse_document(action.document)),
                    }
                )
                if action.parent_id is not None:
                    parent = unit.notes.summary(user_id, action.parent_id, active=True)
                    before = json_object(
                        {"parent_id": parent.id, "version": parent.version, "title": parent.title}
                    )
            elif isinstance(action, PageUpdate):
                page = unit.notes.get(user_id, action.page_id, active=True)
                if page.version != action.expected_version:
                    raise AiConflict("Page changed; request a new preview.")
                before = json_object(
                    {"title": page.title, "document": document_value(page.document)}
                )
                body = (
                    parse_document(action.document)
                    if action.document is not None
                    else page.document
                )
                existing = {block.id: block.type for block in page.document.blocks}
                updated = {block.id: block.type for block in body.blocks}
                if any(updated.get(identifier) != kind for identifier, kind in existing.items()):
                    raise ValueError("Keep existing block IDs and types when editing a page.")
                after = json_object(
                    {
                        "title": page_title(action.title)
                        if action.title is not None
                        else page.title,
                        "document": document_value(body),
                    }
                )
                target = page.id
            elif isinstance(action, (EventCreate, EventUpdate)):
                values = {}
                if isinstance(action, EventUpdate):
                    event = unit.calendar.get_personal_event(user_id, action.event_id)
                    if event.version != action.expected_version:
                        raise AiConflict("Event changed; request a new preview.")
                    values = {name: getattr(event, name) for name in PERSONAL_FIELDS}
                    before = json_object(values)
                    values |= action.changes.model_dump(exclude_unset=True)
                    target = event.id
                else:
                    values = {name: getattr(action, name) for name in PERSONAL_FIELDS}
                after = json_object(personal_values(values))
                if before is not None and before["starts_at"] != after["starts_at"]:
                    warnings = ("existing_reminders_will_be_cancelled",)
            else:
                if action.event_action is not None:
                    event_effect = effects[action.event_action]
                    after = dict(event_effect.after)
                    starts_at = datetime.fromisoformat(str(after["starts_at"]))
                    event_id = event_effect.target_id
                else:
                    assert action.event_id is not None
                    event = unit.reminders.target(user_id, action.source, action.event_id)
                    starts_at, event_id = event.starts_at, action.event_id
                    after = json_object(
                        {
                            "title": event.title,
                            "starts_at": event.starts_at,
                            "ends_at": event.ends_at,
                        }
                    )
                    canonical = (
                        unit.calendar.get_personal_event(user_id, event_id)
                        if action.source == "personal"
                        else unit.calendar.schedule.event(
                            event_id, unit.calendar.academics.get(user_id)
                        )
                    )
                    if action.source == "official":
                        day = event.starts_at.astimezone(ZoneInfo(unit.timezone)).date()
                        resolved = unit.calendar.get_calendar(
                            user_id, day, day, include_hidden=True
                        )
                        after["target_version"] = next(
                            item.version
                            for item in resolved.events
                            if item.source == "official" and item.source_event_id == event_id
                        )
                    after["target_digest"] = hashlib.sha256(
                        json.dumps(
                            json_object(asdict(canonical)),
                            sort_keys=True,
                        ).encode()
                    ).hexdigest()
                after = after | json_object(
                    {
                        "event_id": event_id,
                        "source": action.source,
                        "event_action": action.event_action,
                        "minutes_before": action.minutes_before,
                        "due_at": trigger_time(starts_at, action.minutes_before, self.now()),
                    }
                )
            effects.append(
                ActionEffect(
                    operation=action.operation,
                    target_id=target,
                    before=before,
                    after=after,
                    warnings=warnings,
                )
            )
        return tuple(effects)

    def apply(
        self, unit: ActionContext, user_id: UUID, batch: ActionBatch
    ) -> tuple[ActionOutcome, ...]:
        outcomes: list[ActionOutcome] = []
        for action in batch.actions:
            if isinstance(action, PageCreate):
                result = unit.notes.create(
                    user_id, action.title, parent_id=action.parent_id, document=action.document
                )
            elif isinstance(action, PageUpdate):
                page = unit.notes.get(user_id, action.page_id, active=True)
                result = page
                if action.document is not None:
                    result = unit.notes.replace_document(
                        user_id, page.id, action.document, page.version
                    )
                if action.title is not None:
                    result = unit.notes.update(
                        user_id, page.id, {"title": action.title}, result.version
                    )
            elif isinstance(action, EventCreate):
                result = unit.calendar.create_personal_event(
                    user_id, {name: getattr(action, name) for name in PERSONAL_FIELDS}
                )
            elif isinstance(action, EventUpdate):
                result = unit.calendar.update_personal_event(
                    user_id,
                    action.event_id,
                    action.changes.model_dump(exclude_unset=True),
                    action.expected_version,
                )
            else:
                event_id = (
                    outcomes[action.event_action].target_id
                    if action.event_action is not None
                    else action.event_id
                )
                assert event_id is not None
                result = unit.reminders.create(
                    user_id, action.source, event_id, action.minutes_before
                )
            outcomes.append(ActionOutcome(operation=action.operation, target_id=result.id))
        return tuple(outcomes)
