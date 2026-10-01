from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings


class Base(DeclarativeBase):
    pass


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
