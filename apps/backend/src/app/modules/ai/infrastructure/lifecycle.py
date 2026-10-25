from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentRunner
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.application.recovery import RUN_TIMEOUT
from app.modules.ai.application.sources import SourceReader
from app.modules.ai.domain.state import AiConflict, AiPersistenceUnavailable, Run
from app.modules.ai.infrastructure.action_tools import action_tool
from app.modules.ai.infrastructure.checkpoints import owned_offline_runner
from app.modules.ai.infrastructure.fake_tools import fake_double
from app.modules.ai.infrastructure.grounding import SourceTools
from app.modules.ai.infrastructure.providers import OpenRouterModels
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


class SqlAlchemyAiTransactions:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    @contextmanager
    def __call__(self, user_id: UUID, *, write: bool = False) -> Iterator[AiRepository]:
        try:
            with self.sessions() as database, database.begin():
                users = SqlAlchemyUserAuthentication(database)
                if not (users.lock_active(user_id) if write else users.is_active(user_id)):
                    raise ProfileUnavailable()
                yield SqlAlchemyAiRepository(database)
        except IntegrityError:
            raise AiConflict("AI state changed or a constraint rejected the request.") from None
        except SQLAlchemyError:
            raise AiPersistenceUnavailable("AI state storage is unavailable.") from None


def offline_model() -> FakeChatModel:
    return FakeChatModel(
        responses=(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fake_double",
                        "args": {"value": 7},
                        "id": f"fake-{uuid4().hex}",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Offline test: 7 × 2 = 14."),
        )
    )


class PostgresAgentRunners:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        model: Callable[[], FakeChatModel] = offline_model,
        *,
        real_models: OpenRouterModels | None = None,
        sources: SourceReader | None = None,
        actions_enabled: bool = False,
    ) -> None:
        with sessions() as database:
            engine = database.get_bind()
        if not isinstance(engine, Engine):
            raise ValueError("AI execution requires an engine-backed session factory.")
        self.engine, self.model, self.sessions = engine, model, sessions
        self.real_models = real_models
        self.sources = sources
        self.actions_enabled = actions_enabled

    def instructions(self, user_id: UUID) -> str:
        with SqlAlchemyAiTransactions(self.sessions)(user_id) as repository:
            return repository.preferences(user_id).instructions

    def action_status(self, run: Run, interrupt_id: str) -> str:
        from sqlalchemy import select

        from app.modules.ai.infrastructure.action_models import ActionProposalModel
        from app.modules.ai.infrastructure.actions import SqlAlchemyActions

        with self.sessions.begin() as database:
            row = database.scalar(
                select(ActionProposalModel).where(
                    ActionProposalModel.user_id == run.user_id,
                    ActionProposalModel.conversation_id == run.conversation_id,
                    ActionProposalModel.interrupt_id == interrupt_id,
                )
            )
            proposal = SqlAlchemyActions(database).get(run.user_id, row.id) if row else None
            if proposal is None:
                return "Prior proposal is unavailable. No permission to execute it."
            status = (
                "expired"
                if proposal.status == "pending" and datetime.now(UTC) >= proposal.expires_at
                else proposal.status
            )
            return f"Application proposal {proposal.id}: {status}. Outcomes: " + str(
                [item.model_dump(mode="json") for item in proposal.outcomes]
            )

    @contextmanager
    def __call__(self, run: Run, journal: ExecutionJournal) -> Iterator[AgentRunner]:
        if run.conversation_id is None:
            raise AiConflict("Conversation is unavailable.")
        with self.engine.connect() as storage:
            storage = storage.execution_options(isolation_level="AUTOCOMMIT")
            connection = cast(Connection[DictRow], storage.connection.driver_connection)
            previous = connection.row_factory
            connection.row_factory = dict_row
            try:
                if run.offering_id is not None and self.real_models is None:
                    raise AiConflict("Real model connections are unavailable.")
                models = (
                    self.real_models(run)
                    if self.real_models and run.offering_id is not None
                    else nullcontext(self.model())
                )
                with models as model:
                    source_tools = (
                        SourceTools(self.sources, run.user_id, journal)
                        if self.sources is not None
                        and run.offering_id is not None
                        and self.real_models is not None
                        and self.real_models.access.configuration.offering(
                            run.user_id, run.offering_id
                        ).tools
                        else None
                    )
                    if source_tools is not None:
                        from app.modules.ai.infrastructure.document_context import AnalysisContext

                        source_tools.analysis_context = lambda scope: AnalysisContext(
                            self.sessions
                        ).read(run.user_id, run.conversation_id, scope)
                    tools = (
                        [fake_double]
                        if run.offering_id is None
                        else source_tools.build_tools()
                        if source_tools
                        else []
                    )
                    if self.actions_enabled:
                        tools.append(action_tool())
                    yield owned_offline_runner(
                        connection,
                        run.user_id,
                        run.conversation_id,
                        model,
                        tools,
                        review_tools=frozenset({"propose_actions"})
                        if self.actions_enabled
                        else frozenset(),
                        action_status=lambda interrupt_id: self.action_status(run, interrupt_id),
                        run_id=run.id,
                        journal=journal,
                        sources=source_tools,
                        instructions=lambda: self.instructions(run.user_id),
                        run_timeout=max(
                            0.001,
                            (run.created_at + RUN_TIMEOUT - datetime.now(UTC)).total_seconds(),
                        ),
                    )
            finally:
                connection.row_factory = previous
