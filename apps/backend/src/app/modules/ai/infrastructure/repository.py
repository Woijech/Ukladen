from dataclasses import asdict
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.ai.domain.connections import ConnectionLimited, PersonalConnection
from app.modules.ai.domain.preferences import AssistantPreferences
from app.modules.ai.domain.pricing import PriceSnapshot
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    Conversation,
    ErrorCode,
    ExecutionStatus,
    InvalidAiState,
    Message,
    MessageRole,
    ProviderAttempt,
    Run,
    RunStatus,
    ToolExecution,
    require_run_transition,
)
from app.modules.ai.infrastructure.orm import (
    AssistantPreferencesModel,
    ConnectionBucketModel,
    ConversationModel,
    MessageModel,
    PersonalConnectionModel,
    ProviderAttemptModel,
    RunModel,
    RunReceiptModel,
    ToolExecutionModel,
)
from app.modules.search.domain.evidence import SourceReference


def conversation_entity(row: ConversationModel) -> Conversation:
    return Conversation(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        created_at=row.created_at,
        last_user_message_at=row.last_user_message_at,
        next_sequence=row.next_sequence,
        provider=row.provider,
        model=row.model,
        offering_id=row.offering_id,
        offering_version=row.offering_version,
        connection_id=row.connection_id,
    )


def message_entity(row: MessageModel) -> Message:
    return Message(
        id=row.id,
        user_id=row.user_id,
        conversation_id=row.conversation_id,
        sequence=row.sequence,
        role=cast(MessageRole, row.role),
        content=row.content,
        created_at=row.created_at,
        sources=tuple(SourceReference.model_validate(item) for item in row.sources),
    )


def run_entity(row: RunModel) -> Run:
    return Run(
        price=PriceSnapshot.model_validate(row.price) if row.price else None,
        id=row.id,
        user_id=row.user_id,
        conversation_id=row.conversation_id,
        submission_id=row.submission_id,
        request_digest=row.request_digest,
        provider=row.provider,
        model=row.model,
        status=cast(RunStatus, row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
        version=row.version,
        offering_id=row.offering_id,
        offering_version=row.offering_version,
        connection_id=row.connection_id,
    )


def attempt_entity(row: ProviderAttemptModel) -> ProviderAttempt:
    return ProviderAttempt(
        id=row.id,
        user_id=row.user_id,
        run_id=row.run_id,
        number=row.number,
        status=cast(ExecutionStatus, row.status),
        started_at=row.started_at,
        finished_at=row.finished_at,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        error_code=cast(ErrorCode, row.error_code),
    )


def tool_entity(row: ToolExecutionModel) -> ToolExecution:
    return ToolExecution(
        id=row.id,
        user_id=row.user_id,
        run_id=row.run_id,
        number=row.number,
        call_id=row.call_id,
        tool_name=row.tool_name,
        status=cast(ExecutionStatus, row.status),
        started_at=row.started_at,
        finished_at=row.finished_at,
        error_code=cast(ErrorCode, row.error_code),
    )


class SqlAlchemyAiRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def preferences(self, user_id: UUID) -> AssistantPreferences:
        row = self.session.get(AssistantPreferencesModel, user_id, populate_existing=True)
        return (
            AssistantPreferences(row.instructions, row.version) if row else AssistantPreferences()
        )

    def save_preferences(self, user_id: UUID, value: AssistantPreferences) -> None:
        self.session.merge(AssistantPreferencesModel(user_id=user_id, **asdict(value)))
        self.session.flush()

    def latest_run(self, user_id: UUID, conversation_id: UUID) -> Run | None:
        row = self.session.scalar(
            select(RunModel)
            .where(RunModel.user_id == user_id, RunModel.conversation_id == conversation_id)
            .order_by(RunModel.created_at.desc(), RunModel.id.desc())
            .limit(1)
        )
        return run_entity(row) if row else None

    def save_connection(self, connection: PersonalConnection) -> None:
        self.session.merge(PersonalConnectionModel(**asdict(connection)))
        self.session.flush()

    def get_connection(self, user_id: UUID, connection_id: UUID) -> PersonalConnection | None:
        row = self.session.scalar(
            select(PersonalConnectionModel)
            .where(
                PersonalConnectionModel.id == connection_id,
                PersonalConnectionModel.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        return self._connection(row) if row else None

    @staticmethod
    def _connection(row: PersonalConnectionModel) -> PersonalConnection:
        return PersonalConnection(
            id=row.id,
            user_id=row.user_id,
            label=row.label,
            created_at=row.created_at,
            encrypted_key=row.encrypted_key,
            encryption_key_id=row.encryption_key_id,
            disconnected_at=row.disconnected_at,
        )

    def connections(self, user_id: UUID) -> list[PersonalConnection]:
        return [
            self._connection(row)
            for row in self.session.scalars(
                select(PersonalConnectionModel)
                .where(PersonalConnectionModel.user_id == user_id)
                .order_by(PersonalConnectionModel.created_at, PersonalConnectionModel.id)
                .limit(20)
            )
        ]

    def connection_runs(self, user_id: UUID, connection_id: UUID) -> list[Run]:
        return [
            run_entity(row)
            for row in self.session.scalars(
                select(RunModel).where(
                    RunModel.user_id == user_id,
                    RunModel.connection_id == connection_id,
                    RunModel.status.in_(("queued", "running", "interrupted")),
                )
            )
        ]

    def _bucket(self, scope: str, now: datetime) -> ConnectionBucketModel:
        self.session.execute(
            insert(ConnectionBucketModel)
            .values(
                scope=scope,
                window_start=now,
                requests=0,
            )
            .on_conflict_do_nothing()
        )
        return self.session.scalars(
            select(ConnectionBucketModel)
            .where(ConnectionBucketModel.scope == scope)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    def admit_connection(self, scope: str, limit: int, now: datetime) -> None:
        bucket = self._bucket(scope, now)
        if bucket.blocked_until is not None and now < bucket.blocked_until:
            raise ConnectionLimited(int((bucket.blocked_until - now).total_seconds()) + 1)
        elapsed = (now - bucket.window_start).total_seconds()
        if elapsed >= 60:
            bucket.window_start, bucket.requests = now, 0
        if bucket.requests >= limit:
            raise ConnectionLimited(max(1, int(60 - elapsed) + 1))
        bucket.requests += 1
        self.session.flush()

    def block_connection(self, scope: str, until: datetime) -> None:
        bucket = self._bucket(scope, until)
        if bucket.blocked_until is None or bucket.blocked_until < until:
            bucket.blocked_until = until
        self.session.flush()

    def create_conversation(self, conversation: Conversation) -> None:
        self.session.add(ConversationModel(**asdict(conversation)))
        self.session.flush()

    def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Conversation | None:
        row = self.session.scalar(
            select(ConversationModel)
            .where(ConversationModel.user_id == user_id, ConversationModel.id == conversation_id)
            .execution_options(populate_existing=True)
        )
        return conversation_entity(row) if row else None

    def list_conversations(
        self, user_id: UUID, limit: int, offset: int, active_after: datetime | None = None
    ) -> list[Conversation]:
        if not 1 <= limit <= 200 or not 0 <= offset <= 2**31 - 1:
            raise InvalidAiState("Invalid conversation pagination.")
        from app.modules.ai.infrastructure.review_models import ReviewModel

        statement = select(ConversationModel).where(
            ConversationModel.user_id == user_id,
            ~select(ReviewModel.id)
            .where(
                ReviewModel.conversation_id == ConversationModel.id,
                ReviewModel.discussed.is_(False),
            )
            .exists(),
        )
        if active_after is not None:
            statement = statement.where(
                func.coalesce(ConversationModel.last_user_message_at, ConversationModel.created_at)
                > active_after
            )
        return [
            conversation_entity(row)
            for row in self.session.scalars(
                statement.order_by(ConversationModel.created_at.desc(), ConversationModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def create_document_job(self, run: Run, question: str, selection: dict) -> None:
        from app.modules.ai.infrastructure.document_models import DocumentJobModel

        self.session.add(
            DocumentJobModel(
                run_id=run.id,
                user_id=run.user_id,
                conversation_id=run.conversation_id,
                question=question,
                selection=selection,
            )
        )
        self.session.flush()

    def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> None:
        self.session.execute(
            delete(ConversationModel).where(
                ConversationModel.user_id == user_id, ConversationModel.id == conversation_id
            )
        )

    def active_run(self, user_id: UUID, conversation_id: UUID) -> Run | None:
        row = self.session.scalar(
            select(RunModel)
            .where(
                RunModel.user_id == user_id,
                RunModel.conversation_id == conversation_id,
                RunModel.status.in_(("queued", "running", "interrupted")),
            )
            .execution_options(populate_existing=True)
        )
        return run_entity(row) if row else None

    def append_message(self, message: Message) -> None:
        current = self.get_conversation(message.user_id, message.conversation_id)
        if current is None:
            raise AiNotFound()
        if message.created_at < current.created_at or (
            message.role == "user"
            and current.last_user_message_at is not None
            and message.created_at < current.last_user_message_at
        ):
            raise InvalidAiState("Message activity cannot move backwards.")
        statement = (
            update(ConversationModel)
            .where(
                ConversationModel.id == message.conversation_id,
                ConversationModel.user_id == message.user_id,
                ConversationModel.next_sequence == message.sequence,
            )
            .values(next_sequence=message.sequence + 1)
        )
        if message.role == "user":
            statement = statement.values(last_user_message_at=message.created_at)
        if self.session.scalar(statement.returning(ConversationModel.id)) is None:
            raise AiConflict("Conversation sequence changed.")
        self.session.add(
            MessageModel(
                **(
                    asdict(message)
                    | {"sources": [item.model_dump(mode="json") for item in message.sources]}
                )
            )
        )
        self.session.flush()

    def messages(
        self, user_id: UUID, conversation_id: UUID, after: int, limit: int
    ) -> list[Message]:
        if not 0 <= after <= 2**63 - 1 or not 1 <= limit <= 200:
            raise InvalidAiState("Invalid message pagination.")
        return [
            message_entity(row)
            for row in self.session.scalars(
                select(MessageModel)
                .where(
                    MessageModel.user_id == user_id,
                    MessageModel.conversation_id == conversation_id,
                    MessageModel.sequence > after,
                )
                .order_by(MessageModel.sequence)
                .limit(limit)
            )
        ]

    def recent_messages(
        self, user_id: UUID, conversation_id: UUID, before: int | None, limit: int
    ) -> list[Message]:
        if not 1 <= limit <= 200 or (before is not None and not 1 <= before <= 2**63 - 1):
            raise InvalidAiState("Invalid history pagination.")
        statement = select(MessageModel).where(
            MessageModel.user_id == user_id,
            MessageModel.conversation_id == conversation_id,
        )
        if before is not None:
            statement = statement.where(MessageModel.sequence < before)
        items = list(
            self.session.scalars(statement.order_by(MessageModel.sequence.desc()).limit(limit))
        )
        return [message_entity(row) for row in reversed(items)]

    def create_run(self, run: Run) -> None:
        if run.status != "queued" or run.conversation_id is None:
            raise InvalidAiState("New runs require a conversation and queued state.")
        if (
            self.session.scalar(
                select(RunReceiptModel.run_id).where(
                    RunReceiptModel.user_id == run.user_id,
                    RunReceiptModel.submission_id == run.submission_id,
                )
            )
            is not None
        ):
            raise AiConflict("Submission identifier is retired.")
        if (
            self.session.scalar(
                select(ConversationModel.id)
                .where(
                    ConversationModel.id == run.conversation_id,
                    ConversationModel.user_id == run.user_id,
                )
                .with_for_update()
            )
            is None
        ):
            raise AiNotFound()
        self.session.add(
            RunModel(
                **(
                    asdict(run)
                    | {"price": run.price.model_dump(mode="json") if run.price else None}
                )
            )
        )
        self.session.flush()

    def get_run(self, user_id: UUID, run_id: UUID) -> Run | None:
        row = self.session.scalar(
            select(RunModel)
            .where(RunModel.id == run_id, RunModel.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return run_entity(row) if row else None

    def submission(self, user_id: UUID, submission_id: UUID) -> Run | None:
        row = self.session.scalar(
            select(RunModel)
            .where(RunModel.user_id == user_id, RunModel.submission_id == submission_id)
            .execution_options(populate_existing=True)
        )
        return run_entity(row) if row else None

    def save_run(self, run: Run, expected_status: RunStatus) -> None:
        require_run_transition(expected_status, run.status)
        if (
            self.session.scalar(
                update(RunModel)
                .where(
                    RunModel.id == run.id,
                    RunModel.user_id == run.user_id,
                    RunModel.status == expected_status,
                    RunModel.version == run.version - 1,
                    RunModel.updated_at <= run.updated_at,
                )
                .values(
                    status=run.status,
                    updated_at=run.updated_at,
                    finished_at=run.finished_at,
                    version=run.version,
                )
                .returning(RunModel.id)
            )
            is None
        ):
            raise AiConflict("Run state changed.")

    def create_attempt(self, attempt: ProviderAttempt) -> None:
        if attempt.status != "started":
            raise InvalidAiState("Attempts must be recorded before execution.")
        self.session.add(ProviderAttemptModel(**asdict(attempt)))
        self.session.flush()

    def save_attempt(self, attempt: ProviderAttempt) -> None:
        if attempt.status == "started":
            raise InvalidAiState("An attempt outcome is required.")
        if (
            self.session.scalar(
                update(ProviderAttemptModel)
                .where(
                    ProviderAttemptModel.id == attempt.id,
                    ProviderAttemptModel.user_id == attempt.user_id,
                    ProviderAttemptModel.run_id == attempt.run_id,
                    ProviderAttemptModel.status == "started",
                )
                .values(
                    status=attempt.status,
                    finished_at=attempt.finished_at,
                    input_tokens=attempt.input_tokens,
                    output_tokens=attempt.output_tokens,
                    error_code=attempt.error_code,
                )
                .returning(ProviderAttemptModel.id)
            )
            is None
        ):
            raise AiConflict("Attempt is already finished or unavailable.")

    def attempts(self, user_id: UUID, run_id: UUID) -> list[ProviderAttempt]:
        return [
            attempt_entity(row)
            for row in self.session.scalars(
                select(ProviderAttemptModel)
                .where(
                    ProviderAttemptModel.user_id == user_id, ProviderAttemptModel.run_id == run_id
                )
                .order_by(ProviderAttemptModel.number)
            )
        ]

    def save_interrupted_usage(self, attempt: ProviderAttempt) -> None:
        self.session.execute(
            update(ProviderAttemptModel)
            .where(
                ProviderAttemptModel.id == attempt.id,
                ProviderAttemptModel.user_id == attempt.user_id,
                ProviderAttemptModel.run_id == attempt.run_id,
                ProviderAttemptModel.status == "interrupted",
            )
            .values(
                input_tokens=func.coalesce(ProviderAttemptModel.input_tokens, attempt.input_tokens),
                output_tokens=func.coalesce(
                    ProviderAttemptModel.output_tokens, attempt.output_tokens
                ),
            )
        )

    def create_tool_execution(self, execution: ToolExecution) -> None:
        if execution.status not in ("started", "rejected"):
            raise InvalidAiState("Tool calls must be recorded before execution.")
        self.session.add(ToolExecutionModel(**asdict(execution)))
        self.session.flush()

    def save_tool_execution(self, execution: ToolExecution) -> None:
        if execution.status == "started":
            raise InvalidAiState("A tool outcome is required.")
        if (
            self.session.scalar(
                update(ToolExecutionModel)
                .where(
                    ToolExecutionModel.id == execution.id,
                    ToolExecutionModel.user_id == execution.user_id,
                    ToolExecutionModel.run_id == execution.run_id,
                    ToolExecutionModel.status == "started",
                )
                .values(
                    status=execution.status,
                    finished_at=execution.finished_at,
                    error_code=execution.error_code,
                )
                .returning(ToolExecutionModel.id)
            )
            is None
        ):
            raise AiConflict("Tool call is already finished or unavailable.")

    def tool_executions(self, user_id: UUID, run_id: UUID) -> list[ToolExecution]:
        return [
            tool_entity(row)
            for row in self.session.scalars(
                select(ToolExecutionModel)
                .where(ToolExecutionModel.user_id == user_id, ToolExecutionModel.run_id == run_id)
                .order_by(ToolExecutionModel.number)
            )
        ]
