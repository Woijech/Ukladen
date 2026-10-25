"""Owned request lifecycle; model execution occurs between short transactions."""

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from app.core.logging import log_failure
from app.modules.ai.application.access import (
    AiAccessPolicy,
    AiAccessStatus,
    UnlimitedAiAccessPolicy,
)
from app.modules.ai.application.actions import ActionService
from app.modules.ai.application.agent import AgentInput, AgentResult, AgentRunner
from app.modules.ai.application.connections import ConnectionAccess, ModelOption
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.application.recovery import RUN_TIMEOUT, stop_run
from app.modules.ai.application.streaming import emit
from app.modules.ai.domain.connections import (
    ConnectionUnavailable,
    ModelSelection,
    PersonalConnection,
)
from app.modules.ai.domain.preferences import AssistantPreferences
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    Conversation,
    ErrorCode,
    ExecutionStatus,
    InvalidAiState,
    Message,
    ProviderAttempt,
    Run,
    ToolExecution,
)

logger = logging.getLogger(__name__)


class AiTransactions(Protocol):
    def __call__(
        self, user_id: UUID, *, write: bool = False
    ) -> AbstractContextManager[AiRepository]: ...


class ExecutionJournal(Protocol):
    def start_attempt(self) -> ProviderAttempt: ...
    def finish_attempt(
        self,
        attempt: ProviderAttempt,
        status: ExecutionStatus,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error: ErrorCode | None = None,
    ) -> None: ...
    def start_tool(self, call_id: str, tool_name: str) -> ToolExecution: ...
    def finish_tool(
        self, tool: ToolExecution, status: ExecutionStatus, error: ErrorCode | None = None
    ) -> None: ...
    def check(self) -> None: ...


class AgentRunners(Protocol):
    def __call__(
        self, run: Run, journal: ExecutionJournal
    ) -> AbstractContextManager[AgentRunner]: ...


@dataclass(frozen=True)
class RunSnapshot:
    run: Run
    attempts: tuple[ProviderAttempt, ...]
    tools: tuple[ToolExecution, ...]

    @property
    def estimated_cost(self) -> Decimal | None:
        if self.run.price is None:
            return None
        costs = [
            cost
            for item in self.attempts
            if (cost := self.run.price.estimate(item.input_tokens, item.output_tokens)) is not None
        ]
        return sum(costs, Decimal(0)) if costs else None

    @property
    def unpriced_attempts(self) -> int:
        return sum(
            self.run.price is None or item.input_tokens is None or item.output_tokens is None
            for item in self.attempts
        )


class AiService:
    def __init__(
        self,
        transactions: AiTransactions,
        runners: AgentRunners,
        *,
        provider: str = "fake",
        model: str = "fake-v1",
        connections: ConnectionAccess | None = None,
        access_policy: AiAccessPolicy | None = None,
        actions: ActionService | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.transactions, self.runners = transactions, runners
        self.provider, self.model, self.now = provider, model, now
        self.connections = connections
        self.actions = actions
        self.access_policy = (
            access_policy if access_policy is not None else UnlimitedAiAccessPolicy()
        )

    def conversation(
        self, repository: AiRepository, user_id: UUID, conversation_id: UUID
    ) -> Conversation:
        conversation = repository.get_conversation(user_id, conversation_id)
        if conversation is None or (
            conversation.last_user_message_at or conversation.created_at
        ) <= self.now() - timedelta(days=30):
            raise AiNotFound()
        return conversation

    def create(
        self,
        user_id: UUID,
        title: str,
        *,
        offering_id: str | None = None,
        connection_id: UUID | None = None,
        demo: bool = False,
    ) -> Conversation:
        if demo and (offering_id is not None or connection_id is not None):
            raise InvalidAiState("Demo mode cannot select a real model or connection.")
        if offering_id is None and connection_id is None and not demo:
            default = next((item for item in self.models(user_id) if item.is_default), None)
            if default is not None:
                offering_id = default.id
        with self.transactions(user_id, write=True) as repository:
            selection = ModelSelection()
            provider, model = self.provider, self.model
            if offering_id is not None:
                selection, offering = self.connection_access().select(
                    repository, user_id, offering_id, connection_id
                )
                provider, model = offering.provider, offering.model
            elif connection_id is not None:
                raise InvalidAiState("A model offering is required.")
            conversation = Conversation(
                id=uuid4(),
                user_id=user_id,
                title=title.strip(),
                created_at=self.now(),
                offering_id=selection.offering_id,
                offering_version=selection.offering_version,
                connection_id=selection.connection_id,
                provider=provider,
                model=model,
            )
            repository.create_conversation(conversation)
        return conversation

    def connection_access(self) -> ConnectionAccess:
        if self.connections is None:
            raise ConnectionUnavailable("Real model connections are not configured.")
        return self.connections

    def models(self, user_id: UUID) -> list[ModelOption]:
        return (
            list(self.connections.configuration.model_options(user_id)) if self.connections else []
        )

    def access_status(self, user_id: UUID) -> AiAccessStatus:
        return self.access_policy.status(user_id)

    def personal_connections(self, user_id: UUID) -> list[PersonalConnection]:
        with self.transactions(user_id) as repository:
            return repository.connections(user_id)

    def connect(self, user_id: UUID, label: str, key: str) -> PersonalConnection:
        with self.transactions(user_id, write=True) as repository:
            return self.connection_access().create(repository, user_id, label, key, self.now())

    def disconnect(self, user_id: UUID, connection_id: UUID) -> None:
        with self.transactions(user_id, write=True) as repository:
            self.connection_access().disconnect(repository, user_id, connection_id, self.now())

    def rotate_connection(self, user_id: UUID, connection_id: UUID) -> None:
        with self.transactions(user_id, write=True) as repository:
            self.connection_access().rotate(repository, user_id, connection_id)

    def list(self, user_id: UUID, limit: int, offset: int) -> list[Conversation]:
        with self.transactions(user_id) as repository:
            return repository.list_conversations(
                user_id, limit, offset, self.now() - timedelta(days=30)
            )

    def history(
        self, user_id: UUID, conversation_id: UUID, after: int, limit: int
    ) -> list[Message]:
        with self.transactions(user_id) as repository:
            self.conversation(repository, user_id, conversation_id)
            return repository.messages(user_id, conversation_id, after, limit)

    def preferences(self, user_id: UUID) -> AssistantPreferences:
        with self.transactions(user_id) as repository:
            return repository.preferences(user_id)

    def recent_history(
        self, user_id: UUID, conversation_id: UUID, before: int | None, limit: int
    ) -> list[Message]:
        with self.transactions(user_id) as repository:
            self.conversation(repository, user_id, conversation_id)
            return repository.recent_messages(user_id, conversation_id, before, limit)

    def save_preferences(
        self, user_id: UUID, instructions: str, expected_version: int
    ) -> AssistantPreferences:
        result = AssistantPreferences(instructions, expected_version + 1)
        with self.transactions(user_id, write=True) as repository:
            if repository.preferences(user_id).version != expected_version:
                raise AiConflict("Assistant preferences changed.")
            repository.save_preferences(user_id, result)
        return result

    def conversation_state(
        self, user_id: UUID, conversation_id: UUID
    ) -> tuple[Conversation, Run | None]:
        with self.transactions(user_id) as repository:
            conversation = self.conversation(repository, user_id, conversation_id)
            return conversation, repository.latest_run(user_id, conversation_id)

    def get_run(self, user_id: UUID, run_id: UUID) -> RunSnapshot:
        with self.transactions(user_id) as repository:
            run = repository.get_run(user_id, run_id)
            cutoff = self.now() - timedelta(days=30)
            if run is None or (run.finished_at is not None and run.finished_at <= cutoff):
                raise AiNotFound()
            if run.conversation_id is not None:
                self.conversation(repository, user_id, run.conversation_id)
            return RunSnapshot(
                run,
                tuple(
                    item
                    for item in repository.attempts(user_id, run_id)
                    if (item.finished_at or item.started_at) > cutoff
                ),
                tuple(
                    item
                    for item in repository.tool_executions(user_id, run_id)
                    if (item.finished_at or item.started_at) > cutoff
                ),
            )

    def submit(self, user_id: UUID, request: AgentInput, submission_id: UUID) -> RunSnapshot:
        run, created = self.admit(user_id, request, submission_id)
        if created and not request.full_sources:
            self.execute(run, request)
        return self.get_run(user_id, run.id)

    def admit(self, user_id: UUID, request: AgentInput, submission_id: UUID) -> tuple[Run, bool]:
        payload: list[object] = [str(request.conversation_id), request.message]
        if request.full_sources:
            if (
                request.source_scope is None
                or not (request.source_scope.page_ids or request.source_scope.material_ids)
                or request.source_scope.calendar
                or request.source_scope.database_ids
            ):
                raise InvalidAiState("Select pages/materials for complete-source processing.")
            payload.append("full_sources")
        if request.source_scope is not None:
            payload.append(request.source_scope.model_dump(mode="json"))
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.transactions(user_id, write=True) as repository:
            conversation = self.conversation(repository, user_id, request.conversation_id)
            existing = repository.submission(user_id, submission_id)
            if existing is not None:
                if (
                    existing.finished_at is not None
                    and existing.finished_at <= self.now() - timedelta(days=30)
                ):
                    raise AiConflict("Submission identifier is retired.")
                if existing.request_digest != digest:
                    raise AiConflict("Submission identifier was already used.")
                run = existing
            else:
                if repository.active_run(user_id, conversation.id) is not None:
                    raise AiConflict("Conversation already has active execution.")
                now = self.now()
                self.access_policy.admit(user_id, repository, now)
                provider, model = self.provider, self.model
                price = None
                if conversation.offering_id is not None:
                    offering, _ = self.connection_access().check(
                        repository, user_id, conversation, now
                    )
                    provider, model = offering.provider, offering.model
                    price = offering.price
                run = Run(
                    price=price,
                    id=uuid4(),
                    user_id=user_id,
                    conversation_id=conversation.id,
                    submission_id=submission_id,
                    request_digest=digest,
                    provider=provider,
                    model=model,
                    offering_id=conversation.offering_id,
                    offering_version=conversation.offering_version,
                    connection_id=conversation.connection_id,
                    status="queued",
                    created_at=now,
                    updated_at=now,
                )
                repository.create_run(run)
                if request.full_sources:
                    assert request.source_scope is not None
                    repository.create_document_job(
                        run, request.message, request.source_scope.model_dump(mode="json")
                    )
                repository.append_message(
                    Message(
                        id=uuid4(),
                        user_id=user_id,
                        conversation_id=conversation.id,
                        sequence=conversation.next_sequence,
                        role="user",
                        content=request.message,
                        created_at=now,
                    )
                )
        return run, existing is None

    def execute(self, run: Run, request: AgentInput) -> None:
        with self.transactions(run.user_id, write=True) as repository:
            current = repository.get_run(run.user_id, run.id)
            if current is None or current.status != "queued":
                return
            if self.now() >= current.created_at + RUN_TIMEOUT:
                stop_run(repository, current, self.now(), status="failed", error="timeout")
                return
            self.conversation(repository, run.user_id, request.conversation_id)
            run = current.transition("running", self.now())
            repository.save_run(run, "queued")
        journal = RunJournal(self, run)
        try:
            with self.runners(run, journal) as runner:
                result = runner.run(request)
            if result.status == "interrupted" and result.review and self.actions is not None:
                self.actions.propose(run, result.review, result.sources)
                result = AgentResult(
                    status="completed",
                    answer=(
                        "Предложение готово. Проверь все изменения и нажми «Применить всё» "
                        "или «Отклонить». До подтверждения данные не меняются."
                    ),
                    sources=result.sources,
                )
        except Exception as error:
            log_failure(logger, "ai.execution_failed", error)
            result = AgentResult(status="failed")
        with self.transactions(run.user_id, write=True) as repository:
            current = repository.get_run(run.user_id, run.id)
            if current is None or current.status != "running":
                return
            conversation = self.conversation(repository, run.user_id, request.conversation_id)
            if self.now() >= current.created_at + RUN_TIMEOUT:
                result = AgentResult(status="failed", error_code="timeout")
            if result.status not in {"completed", "interrupted"}:
                stop_run(
                    repository,
                    current,
                    self.now(),
                    status="failed",
                    error=result.error_code or "unavailable",
                )
                return
            status = "interrupted" if result.status == "interrupted" else "failed"
            if result.status == "completed" and result.answer:
                repository.append_message(
                    Message(
                        id=uuid4(),
                        user_id=run.user_id,
                        conversation_id=conversation.id,
                        sequence=conversation.next_sequence,
                        role="assistant",
                        content=result.answer,
                        created_at=self.now(),
                        sources=result.sources,
                    )
                )
                status = "completed"
            repository.save_run(current.transition(status, self.now()), "running")

    def interrupt(self, repository: AiRepository, run: Run) -> Run:
        return stop_run(repository, run, self.now(), status="cancelled", error="cancelled")

    def cancel(self, user_id: UUID, run_id: UUID) -> RunSnapshot:
        with self.transactions(user_id, write=True) as repository:
            run = repository.get_run(user_id, run_id)
            if run is None:
                raise AiNotFound()
            if run.conversation_id is not None:
                self.conversation(repository, user_id, run.conversation_id)
            self.interrupt(repository, run)
        return self.get_run(user_id, run_id)

    def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        with self.transactions(user_id, write=True) as repository:
            self.conversation(repository, user_id, conversation_id)
            run = repository.active_run(user_id, conversation_id)
            if run is not None:
                self.interrupt(repository, run)
            repository.delete_conversation(user_id, conversation_id)


class RunJournal:
    def __init__(self, service: AiService, run: Run, *, background: bool = False) -> None:
        self.service, self.run, self.background = service, run, background

    def current(self, repository: AiRepository) -> Run:
        run = repository.get_run(self.run.user_id, self.run.id)
        if run is None or run.status != "running" or run.conversation_id is None:
            raise AiConflict("Execution is no longer active.")
        if not self.background and self.service.now() >= run.created_at + RUN_TIMEOUT:
            raise TimeoutError("AI execution deadline exceeded.")
        self.service.conversation(repository, run.user_id, run.conversation_id)
        return run

    def check(self) -> None:
        with self.service.transactions(self.run.user_id) as repository:
            self.current(repository)

    def start_attempt(self) -> ProviderAttempt:
        with self.service.transactions(self.run.user_id, write=True) as repository:
            run = self.current(repository)
            number = len(repository.attempts(run.user_id, run.id)) + 1
            if number > 4 and not self.background:
                raise AiConflict("Provider attempt budget exhausted.")
            if run.offering_id is not None:
                self.service.connection_access().check(
                    repository, run.user_id, run, self.service.now(), admit=True
                )
            attempt = ProviderAttempt(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=number,
                status="started",
                started_at=self.service.now(),
            )
            repository.create_attempt(attempt)
        emit("progress", kind="model", number=number, status="started")
        return attempt

    def finish_attempt(
        self,
        attempt: ProviderAttempt,
        status: ExecutionStatus,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error: ErrorCode | None = None,
    ) -> None:
        with self.service.transactions(self.run.user_id, write=True) as repository:
            stored = next(
                (
                    item
                    for item in repository.attempts(attempt.user_id, attempt.run_id)
                    if item.id == attempt.id
                ),
                None,
            )
            if stored is not None and stored.status == "started":
                repository.save_attempt(
                    replace(
                        stored,
                        status=status,
                        finished_at=self.service.now(),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        error_code=error,
                    )
                )
            elif (
                stored is not None
                and stored.status == "interrupted"
                and stored.finished_at is not None
                and stored.finished_at > self.service.now() - timedelta(days=30)
            ):
                repository.save_interrupted_usage(
                    replace(stored, input_tokens=input_tokens, output_tokens=output_tokens)
                )

    def start_tool(self, call_id: str, tool_name: str) -> ToolExecution:
        with self.service.transactions(self.run.user_id, write=True) as repository:
            run = self.current(repository)
            number = len(repository.tool_executions(run.user_id, run.id)) + 1
            if number > 8:
                raise AiConflict("Tool call budget exhausted.")
            tool = ToolExecution(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=number,
                call_id=call_id,
                tool_name=tool_name,
                status="started",
                started_at=self.service.now(),
            )
            repository.create_tool_execution(tool)
        emit("progress", kind="tool", name=tool_name, number=number, status="started")
        return tool

    def finish_tool(
        self, tool: ToolExecution, status: ExecutionStatus, error: ErrorCode | None = None
    ) -> None:
        with self.service.transactions(self.run.user_id, write=True) as repository:
            stored = next(
                (
                    item
                    for item in repository.tool_executions(tool.user_id, tool.run_id)
                    if item.id == tool.id
                ),
                None,
            )
            if stored is not None and stored.status == "started":
                repository.save_tool_execution(
                    replace(stored, status=status, finished_at=self.service.now(), error_code=error)
                )
