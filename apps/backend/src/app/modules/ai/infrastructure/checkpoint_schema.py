"""Pinned PostgreSQL checkpointer 3.2.0 schema; changes require an Alembic revision."""

from sqlalchemy import Column, ForeignKey, Index, Integer, LargeBinary, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base

CHECKPOINT_SCHEMA_VERSION = 9

checkpoint_migrations = Table(
    "checkpoint_migrations", Base.metadata, Column("v", Integer, primary_key=True)
)
checkpoints = Table(
    "checkpoints",
    Base.metadata,
    Column(
        "thread_id",
        Text,
        ForeignKey("ai_conversations.checkpoint_thread_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("checkpoint_ns", Text, primary_key=True, server_default=""),
    Column("checkpoint_id", Text, primary_key=True),
    Column("parent_checkpoint_id", Text),
    Column("type", Text),
    Column("checkpoint", JSONB, nullable=False),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Index("checkpoints_thread_id_idx", "thread_id"),
)
checkpoint_blobs = Table(
    "checkpoint_blobs",
    Base.metadata,
    Column(
        "thread_id",
        Text,
        ForeignKey("ai_conversations.checkpoint_thread_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("checkpoint_ns", Text, primary_key=True, server_default=""),
    Column("channel", Text, primary_key=True),
    Column("version", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("blob", LargeBinary),
    Index("checkpoint_blobs_thread_id_idx", "thread_id"),
)
checkpoint_writes = Table(
    "checkpoint_writes",
    Base.metadata,
    Column(
        "thread_id",
        Text,
        ForeignKey("ai_conversations.checkpoint_thread_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("checkpoint_ns", Text, primary_key=True, server_default=""),
    Column("checkpoint_id", Text, primary_key=True),
    Column("task_id", Text, primary_key=True),
    Column("idx", Integer, primary_key=True),
    Column("channel", Text, nullable=False),
    Column("type", Text),
    Column("blob", LargeBinary, nullable=False),
    Column("task_path", Text, nullable=False, server_default=""),
    Index("checkpoint_writes_thread_id_idx", "thread_id"),
)
