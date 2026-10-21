"""Owned request lifecycle; model execution occurs between short transactions."""

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from app.core.logging import log_failure
from app.modules.ai.application.agent import AgentInput, AgentResult, AgentRunner
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.domain.state import (
    ACTIVE_RUN_STATUSES,
    AiConflict,
    AiNotFound,
    Conversation,
    ErrorCode,
    ExecutionStatus,
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


class AiService:
    def __init__(
        self,
        transactions: AiTransactions,
        runners: AgentRunners,
        *,
        provider: str = "fake",
        model: str = "fake-v1",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.transactions, self.runners = transactions, runners
        self.provider, self.model, self.now = provider, model, now

    def conversation(
        self, repository: AiRepository, user_id: UUID, conversation_id: UUID
    ) -> Conversation:
        conversation = repository.get_conversation(user_id, conversation_id)
        if conversation is None or (
            conversation.last_user_message_at or conversation.created_at
        ) <= self.now() - timedelta(days=30):
            raise AiNotFound()
        return conversation

    def create(self, user_id: UUID, title: str) -> Conversation:
        conversation = Conversation(
            id=uuid4(), user_id=user_id, title=title.strip(), created_at=self.now()
        )
        with self.transactions(user_id, write=True) as repository:
            repository.create_conversation(conversation)
        return conversation

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

    def get_run(self, user_id: UUID, run_id: UUID) -> RunSnapshot:
        with self.transactions(user_id) as repository:
            run = repository.get_run(user_id, run_id)
            if run is None:
                raise AiNotFound()
            if run.conversation_id is not None:
                self.conversation(repository, user_id, run.conversation_id)
            return RunSnapshot(
                run,
                tuple(repository.attempts(user_id, run_id)),
                tuple(repository.tool_executions(user_id, run_id)),
            )

    def submit(self, user_id: UUID, request: AgentInput, submission_id: UUID) -> RunSnapshot:
        digest = hashlib.sha256(
            json.dumps(
                [str(request.conversation_id), request.message],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.transactions(user_id, write=True) as repository:
            conversation = self.conversation(repository, user_id, request.conversation_id)
            existing = repository.submission(user_id, submission_id)
            if existing is not None:
                if existing.request_digest != digest:
                    raise AiConflict("Submission identifier was already used.")
                run = existing
            else:
                if repository.active_run(user_id, conversation.id) is not None:
                    raise AiConflict("Conversation already has active execution.")
                now = self.now()
                run = Run(
                    id=uuid4(),
                    user_id=user_id,
                    conversation_id=conversation.id,
                    submission_id=submission_id,
                    request_digest=digest,
                    provider=self.provider,
                    model=self.model,
                    status="queued",
                    created_at=now,
                    updated_at=now,
                )
                repository.create_run(run)
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
        if existing is None:
            self.execute(run, request)
        return self.get_run(user_id, run.id)

    def execute(self, run: Run, request: AgentInput) -> None:
        with self.transactions(run.user_id, write=True) as repository:
            current = repository.get_run(run.user_id, run.id)
            if current is None or current.status != "queued":
                return
            self.conversation(repository, run.user_id, request.conversation_id)
            run = current.transition("running", self.now())
            repository.save_run(run, "queued")
        journal = RunJournal(self, run)
        try:
            with self.runners(run, journal) as runner:
                result = runner.run(request)
        except Exception as error:
            log_failure(logger, "ai.execution_failed", error)
            result = AgentResult(status="failed")
        with self.transactions(run.user_id, write=True) as repository:
            current = repository.get_run(run.user_id, run.id)
            if current is None or current.status != "running":
                return
            conversation = self.conversation(repository, run.user_id, request.conversation_id)
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
                    )
                )
                status = "completed"
            repository.save_run(current.transition(status, self.now()), "running")

    def interrupt(self, repository: AiRepository, run: Run) -> Run:
        if run.status not in ACTIVE_RUN_STATUSES:
            return run
        now = self.now()
        for attempt in repository.attempts(run.user_id, run.id):
            if attempt.status == "started":
                repository.save_attempt(
                    replace(attempt, status="interrupted", finished_at=now, error_code="cancelled")
                )
        for tool in repository.tool_executions(run.user_id, run.id):
            if tool.status == "started":
                repository.save_tool_execution(
                    replace(tool, status="interrupted", finished_at=now, error_code="cancelled")
                )
        cancelled = run.transition("cancelled", now)
        repository.save_run(cancelled, run.status)
        return cancelled

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
    def __init__(self, service: AiService, run: Run) -> None:
        self.service, self.run = service, run

    def current(self, repository: AiRepository) -> Run:
        run = repository.get_run(self.run.user_id, self.run.id)
        if run is None or run.status != "running" or run.conversation_id is None:
            raise AiConflict("Execution is no longer active.")
        self.service.conversation(repository, run.user_id, run.conversation_id)
        return run

    def check(self) -> None:
        with self.service.transactions(self.run.user_id) as repository:
            self.current(repository)

    def start_attempt(self) -> ProviderAttempt:
        with self.service.transactions(self.run.user_id, write=True) as repository:
            run = self.current(repository)
            number = len(repository.attempts(run.user_id, run.id)) + 1
            if number > 4:
                raise AiConflict("Provider attempt budget exhausted.")
            attempt = ProviderAttempt(
                id=uuid4(),
                user_id=run.user_id,
                run_id=run.id,
                number=number,
                status="started",
                started_at=self.service.now(),
            )
            repository.create_attempt(attempt)
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
