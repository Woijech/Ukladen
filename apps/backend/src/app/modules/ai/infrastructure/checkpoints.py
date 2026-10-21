"""Owner-bound adapter for the pinned checkpointer; all cursors use short transactions."""

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    DeltaChannelHistory,
)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection, Cursor, Error
from psycopg.pq import TransactionStatus
from psycopg.rows import DictRow

from app.core.logging import log_failure
from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.agent import AgentRunner
from app.modules.ai.application.lifecycle import ExecutionJournal
from app.modules.ai.domain.state import (
    AiConflict,
    AiNotFound,
    AiPersistenceUnavailable,
    require_time,
)
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.checkpoint_schema import CHECKPOINT_SCHEMA_VERSION

logger = logging.getLogger(__name__)


class OwnedPostgresSaver(PostgresSaver):
    def __init__(
        self,
        connection: Connection[DictRow],
        user_id: UUID,
        conversation_id: UUID,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        run_id: UUID | None = None,
    ) -> None:
        if (
            not connection.autocommit
            or connection.info.transaction_status != TransactionStatus.IDLE
        ):
            raise ValueError(
                "Checkpoints need an autocommit connection without an outer transaction."
            )
        self.user_id, self.conversation_id, self.now = user_id, conversation_id, now
        self.run_id = run_id
        super().__init__(
            connection, serde=JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=[])
        )

    def setup(self) -> None:
        raise AiConflict("Checkpoint schema is managed through Alembic.")

    def validate_schema(self) -> None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT count(*) AS count, min(v) AS first, max(v) AS last "
                "FROM checkpoint_migrations"
            ).fetchone()
            if row is None or (row["count"], row["first"], row["last"]) != (
                CHECKPOINT_SCHEMA_VERSION + 1,
                0,
                CHECKPOINT_SCHEMA_VERSION,
            ):
                raise AiPersistenceUnavailable("Checkpoint migration version does not match.")

    @contextmanager
    def _cursor(self, *, pipeline: bool = False) -> Iterator[Cursor[DictRow]]:
        try:
            # A single transaction covers authorization and every write in this checkpoint batch.
            with super()._cursor(pipeline=False) as cursor, cursor.connection.transaction():
                instant = self.now()
                require_time(instant)
                owner = cursor.execute(
                    "SELECT id FROM users WHERE id = %s AND status = 'active' FOR SHARE",
                    (self.user_id,),
                ).fetchone()
                conversation = (
                    None
                    if owner is None
                    else cursor.execute(
                        "SELECT id FROM ai_conversations WHERE id = %s AND user_id = %s "
                        "AND coalesce(last_user_message_at, created_at) > %s FOR SHARE",
                        (self.conversation_id, self.user_id, instant - timedelta(days=30)),
                    ).fetchone()
                )
                if conversation is None:
                    raise AiNotFound()
                if (
                    self.run_id is not None
                    and cursor.execute(
                        "SELECT id FROM ai_runs WHERE id = %s AND user_id = %s "
                        "AND conversation_id = %s AND status = 'running' FOR SHARE",
                        (self.run_id, self.user_id, self.conversation_id),
                    ).fetchone()
                    is None
                ):
                    raise AiNotFound()
                yield cursor
        except Error as error:
            log_failure(logger, "ai.checkpoint_storage_failed", error)
            raise AiPersistenceUnavailable("AI state storage is unavailable.") from None

    def _require_config(self, config: RunnableConfig | None) -> None:
        if config is None or config.get("configurable", {}).get("thread_id") != str(
            self.conversation_id
        ):
            raise AiNotFound()

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        self._require_config(config)
        if self.run_id is not None and not config.get("configurable", {}).get("checkpoint_id"):
            # Failed/cancelled branches cannot become the context for a new submission.
            with self._cursor() as cursor:
                row = cursor.execute(
                    "SELECT c.checkpoint_id FROM checkpoints c JOIN ai_runs r "
                    "ON r.id::text = c.metadata->>'ukladen_run_id' "
                    "WHERE c.thread_id = %s AND c.checkpoint_ns = %s AND r.user_id = %s "
                    "AND (r.id = %s OR r.status = 'completed') "
                    "ORDER BY c.checkpoint_id DESC LIMIT 1",
                    (
                        str(self.conversation_id),
                        config.get("configurable", {}).get("checkpoint_ns", ""),
                        self.user_id,
                        self.run_id,
                    ),
                ).fetchone()
            if row is None:
                return None
            config = {
                **config,
                "configurable": {
                    **config.get("configurable", {}),
                    "checkpoint_id": row["checkpoint_id"],
                },
            }
        return super().get_tuple(config)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        self._require_config(config)
        if before is not None:
            self._require_config(before)
        if limit is None:
            limit = 100
        if not 1 <= limit <= 200:
            raise ValueError("Invalid checkpoint pagination.")
        yield from super().list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        self._require_config(config)
        return super().put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._require_config(config)
        super().put_writes(config, writes, task_id, task_path)

    def get_delta_channel_history(
        self,
        *,
        config: RunnableConfig,
        channels: Sequence[str],
    ) -> Mapping[str, DeltaChannelHistory]:
        self._require_config(config)
        return super().get_delta_channel_history(config=config, channels=channels)

    def delete_thread(self, thread_id: str) -> None:
        raise AiConflict("Delete content through the conversation lifecycle.")

    def delete_for_runs(self, run_ids: Sequence[str]) -> None:
        raise AiConflict("Delete content through the conversation lifecycle.")

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        raise AiConflict("Conversation copying is unavailable.")

    def prune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        raise AiConflict("Delete content through the conversation lifecycle.")


def owned_offline_runner(
    connection: Connection[DictRow],
    user_id: UUID,
    conversation_id: UUID,
    model: FakeChatModel,
    tools: Sequence[BaseTool],
    *,
    review_tools: frozenset[str] = frozenset(),
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    run_id: UUID | None = None,
    journal: ExecutionJournal | None = None,
) -> AgentRunner:
    """Caller owns the connection; no connection creation or DDL occurs here."""
    saver = OwnedPostgresSaver(connection, user_id, conversation_id, now=now, run_id=run_id)
    saver.validate_schema()
    return OfflineAgentRunner(
        model, tools, saver, review_tools=review_tools, run_id=run_id, journal=journal
    )
