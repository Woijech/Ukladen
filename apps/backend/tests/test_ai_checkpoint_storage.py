import io
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection, OperationalError
from psycopg.pq import TransactionStatus
from psycopg.rows import DictRow
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.session import Base
from app.modules.ai.domain.state import AiConflict, AiNotFound, AiPersistenceUnavailable
from app.modules.ai.infrastructure import checkpoint_schema
from app.modules.ai.infrastructure import orm as ai_orm
from app.modules.ai.infrastructure.checkpoints import OwnedPostgresSaver
from app.modules.users.infrastructure import orm as users_orm  # noqa: F401

NOW = datetime(2026, 10, 22, 9, tzinfo=UTC)
TABLES = {
    "ai_conversations",
    "ai_messages",
    "ai_runs",
    "ai_provider_attempts",
    "ai_tool_executions",
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
}


def connection_mock() -> MagicMock:
    connection = MagicMock(spec=Connection)
    connection.autocommit = True
    connection.info = MagicMock(transaction_status=TransactionStatus.IDLE)
    return connection


def saver(connection: MagicMock | None = None) -> OwnedPostgresSaver:
    return OwnedPostgresSaver(
        cast(Connection[DictRow], connection or connection_mock()),
        uuid4(),
        uuid4(),
        now=lambda: NOW,
    )


def test_owner_foreign_keys_and_independent_execution_retention_compile_for_postgres() -> None:
    assert ai_orm.ConversationModel.__tablename__ in TABLES
    for name in TABLES:
        ddl = str(CreateTable(Base.metadata.tables[name]).compile(dialect=dialect()))
        assert f"CREATE TABLE {name}" in ddl
    for name in ("ai_messages", "ai_runs", "ai_provider_attempts", "ai_tool_executions"):
        table = Base.metadata.tables[name]
        assert any(
            "user_id" in fk.column_keys and len(fk.column_keys) == 2
            for fk in table.foreign_key_constraints
        )
    run_table = Base.metadata.tables["ai_runs"]
    run_sql = str(CreateTable(run_table).compile(dialect=dialect()))
    assert "ON DELETE SET NULL (conversation_id)" in run_sql
    assert "UNIQUE (user_id, submission_id)" in run_sql
    active = next(index for index in run_table.indexes if index.name == "uq_ai_runs_active")
    ddl = str(CreateIndex(active).compile(dialect=dialect()))
    assert "UNIQUE" in ddl and "('queued', 'running', 'interrupted')" in ddl
    for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        table = Base.metadata.tables[name]
        assert any(
            fk.referred_table.name == "ai_conversations" and fk.ondelete == "CASCADE"
            for fk in table.foreign_key_constraints
        )
    for name in ("ai_runs", "ai_provider_attempts", "ai_tool_executions"):
        assert set(Base.metadata.tables[name].columns.keys()).isdisjoint(
            {
                "content",
                "prompt",
                "arguments",
                "response",
                "api_key",
                "metadata",
            }
        )


def test_pinned_checkpoint_columns_and_schema_version_match_the_installed_package() -> None:
    assert len(PostgresSaver.MIGRATIONS) == checkpoint_schema.CHECKPOINT_SCHEMA_VERSION + 1 == 10
    assert checkpoint_schema.checkpoint_blobs.c.blob.nullable
    assert checkpoint_schema.checkpoint_writes.c.task_path.server_default is not None
    assert checkpoint_schema.checkpoints.c.checkpoint.type.__class__.__name__ == "JSONB"
    assert set(checkpoint_schema.checkpoint_writes.primary_key.columns.keys()) == {
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "task_id",
        "idx",
    }


def test_migration_generates_sql_only_and_refuses_a_destructive_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0022_ai_persistence"]
    revision = scripts.get_revision("0022_ai_persistence")
    assert revision is not None and revision.down_revision == "0021_google_email_confirmations"
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={
            "as_sql": True,
            "output_buffer": buffer,
        },
    )
    monkeypatch.setattr(revision.module, "op", Operations(context))
    revision.module.upgrade()
    sql = buffer.getvalue()
    assert sql.count("CREATE TABLE") == 9
    for name in TABLES:
        assert f"CREATE TABLE {name}" in sql
    assert "SELECT generate_series(0, 9)" in sql
    assert "SET NULL (conversation_id)" in sql
    assert "DROP TABLE" not in sql and "UPDATE users" not in sql
    buffer.truncate(0)
    buffer.seek(0)
    revision.module.downgrade()
    sql = buffer.getvalue()
    assert (
        sql.index("ACCESS EXCLUSIVE MODE") < sql.index("RAISE EXCEPTION") < sql.index("DROP TABLE")
    )
    assert "IF EXISTS (SELECT 1 FROM ai_conversations)" in sql
    assert "EXISTS (SELECT 1 FROM checkpoint_writes)" in sql
    assert sql.count("DROP TABLE") == 9


def test_owned_saver_rejects_cross_thread_and_unscoped_reads_before_driver_access() -> None:
    store = saver()
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid4())}}
    for operation in (
        lambda: store.get_tuple(config),
        lambda: list(store.list(None)),
        lambda: list(store.list(config)),
        lambda: store.put(config, empty_checkpoint(), {}, {}),
        lambda: store.put_writes(config, [], "task"),
        lambda: store.get_delta_channel_history(config=config, channels=[]),
    ):
        with pytest.raises(AiNotFound):
            operation()


def test_schema_ddl_copy_and_unscoped_cleanup_are_disabled() -> None:
    store = saver()
    for operation in (
        store.setup,
        lambda: store.delete_thread(str(store.conversation_id)),
        lambda: store.delete_for_runs([]),
        lambda: store.copy_thread("a", "b"),
        lambda: store.prune([]),
    ):
        with pytest.raises(AiConflict):
            operation()
    connection = connection_mock()
    connection.autocommit = False
    with pytest.raises(ValueError):
        saver(connection)
    connection.autocommit = True
    connection.info.transaction_status = TransactionStatus.INTRANS
    with pytest.raises(ValueError):
        saver(connection)


@pytest.mark.parametrize("missing", ["owner", "conversation", None])
def test_each_cursor_checks_active_owner_and_expiry_inside_its_short_transaction(
    monkeypatch: pytest.MonkeyPatch,
    missing: str | None,
) -> None:
    store = saver()
    cursor = MagicMock()
    cursor.execute.return_value = cursor
    cursor.fetchone.side_effect = (
        [None]
        if missing == "owner"
        else [
            {"id": store.user_id},
            None if missing == "conversation" else {"id": store.conversation_id},
        ]
    )
    events = []
    cursor.connection.transaction.return_value.__enter__.side_effect = lambda: events.append(
        "begin"
    )
    cursor.connection.transaction.return_value.__exit__.side_effect = lambda *args: events.append(
        "end"
    )

    @contextmanager
    def raw_cursor(self, *, pipeline=False):
        assert not pipeline
        yield cursor

    monkeypatch.setattr(PostgresSaver, "_cursor", raw_cursor)

    def access():
        with store._cursor(pipeline=True):
            assert events == ["begin"]
            events.append("checkpoint-write")

    if missing:
        with pytest.raises(AiNotFound):
            access()
        assert events == ["begin", "end"]
    else:
        access()
        assert events == ["begin", "checkpoint-write", "end"]
        query, parameters = cursor.execute.call_args.args
        assert "FOR SHARE" in query and " > %s" in query
        assert parameters == (store.conversation_id, store.user_id, NOW - timedelta(days=30))


@pytest.mark.parametrize("compatible", [True, False])
def test_schema_version_is_checked_without_automatic_setup(
    monkeypatch: pytest.MonkeyPatch,
    compatible: bool,
) -> None:
    store = saver()
    cursor = MagicMock()
    cursor.execute.return_value = cursor
    cursor.fetchone.return_value = {"count": 10, "first": 0, "last": 9 if compatible else 10}

    @contextmanager
    def raw_cursor(*args, **kwargs):
        yield cursor

    monkeypatch.setattr(store, "_cursor", raw_cursor)
    if compatible:
        store.validate_schema()
    else:
        with pytest.raises(AiPersistenceUnavailable):
            store.validate_schema()
    assert all("SELECT" in call.args[0] for call in cursor.execute.call_args_list)


def test_database_exception_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    store = saver()

    @contextmanager
    def fail(*args, **kwargs):
        raise OperationalError("private-connection-details")
        yield

    monkeypatch.setattr(PostgresSaver, "_cursor", fail)
    with pytest.raises(AiPersistenceUnavailable) as error:
        with store._cursor():
            pytest.fail("Driver failure must stop checkpoint access")
    assert "private" not in str(error.value) and error.value.__suppress_context__
