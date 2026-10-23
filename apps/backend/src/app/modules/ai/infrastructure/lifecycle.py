from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
from app.modules.ai.domain.state import AiConflict, AiPersistenceUnavailable, Run
from app.modules.ai.infrastructure.checkpoints import owned_offline_runner
from app.modules.ai.infrastructure.fake_tools import fake_double
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
        self, sessions: sessionmaker[Session], model: Callable[[], FakeChatModel] = offline_model
    ) -> None:
        with sessions() as database:
            engine = database.get_bind()
        if not isinstance(engine, Engine):
            raise ValueError("AI execution requires an engine-backed session factory.")
        self.engine, self.model = engine, model

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
                yield owned_offline_runner(
                    connection,
                    run.user_id,
                    run.conversation_id,
                    self.model(),
                    [fake_double],
                    run_id=run.id,
                    journal=journal,
                    run_timeout=max(
                        0.001, (run.created_at + RUN_TIMEOUT - datetime.now(UTC)).total_seconds()
                    ),
                )
            finally:
                connection.row_factory = previous
