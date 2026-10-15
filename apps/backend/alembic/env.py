import logging

from alembic import context
from app.core.config import get_settings
from app.core.logging import configure_logging, log_failure
from app.db.session import Base, create_database_engine
from app.modules.academics.infrastructure import orm as academics_orm  # noqa: F401
from app.modules.auth.infrastructure import orm as auth_orm  # noqa: F401
from app.modules.calendar.infrastructure import orm as calendar_orm  # noqa: F401
from app.modules.materials.infrastructure import orm as materials_orm  # noqa: F401
from app.modules.notes.infrastructure import orm as notes_orm  # noqa: F401
from app.modules.notifications.infrastructure import orm as notifications_orm  # noqa: F401
from app.modules.relations.infrastructure import orm as relations_orm  # noqa: F401
from app.modules.reminders.infrastructure import orm as reminders_orm  # noqa: F401
from app.modules.schedule.infrastructure import orm as schedule_orm  # noqa: F401
from app.modules.users.infrastructure import orm as users_orm  # noqa: F401
from app.modules.workspace.infrastructure import orm as workspace_orm  # noqa: F401

config = context.config
# A CLI migration configures its own process. Embedded migrations preserve the
# host's handlers and loggers; fileConfig would disable application diagnostics.
if config.attributes.get("connection") is None:
    configure_logging(get_settings().log_level)

logger = logging.getLogger("app.db.migrations")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_database_engine(get_settings())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


logger.info("database.migration_started")
try:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
except Exception as error:
    log_failure(logger, "database.migration_failed", error)
    raise
else:
    logger.info("database.migration_completed")
