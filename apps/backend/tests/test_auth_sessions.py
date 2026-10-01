import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema
from test_auth_persistence import migration_config

from alembic import command
from app.core.config import Settings
from app.modules.auth.application.ports import (
    SessionCache,
    SessionCacheUnavailable,
    SessionRepository,
)
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.infrastructure.repository import SqlAlchemySessionRepository
from app.modules.auth.infrastructure.session_cache import RedisSessionCache
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.infrastructure.orm import UserModel

NOW = datetime.now(UTC)


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql+psycopg://test:test@localhost:5432/test",
            "redis_url": "redis://localhost:6379/0",
            "s3_endpoint": "http://localhost:8333",
            "s3_access_key": "test",
            "s3_secret_key": "test",
            "s3_bucket": "test",
            "auth_session_ttl_seconds": 30 * 24 * 60 * 60,
        }
    )


@pytest.fixture
def cache() -> Mock:
    sessions: dict[str, AuthSession] = {}
    mock = create_autospec(SessionCache, instance=True)
    mock.get.side_effect = sessions.get
    mock.set.side_effect = lambda session: sessions.__setitem__(session.token_hash, session)
    mock.delete.side_effect = lambda *hashes: [
        sessions.pop(token_hash, None) for token_hash in hashes
    ]
    return mock


def service(
    repository: SessionRepository, cache: SessionCache, settings: Settings
) -> SessionService:
    return SessionService(
        repository,
        cache,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
        now=lambda: NOW,
    )


def test_creation_validation_and_cache_hit(settings: Settings, cache: Mock) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    assert Settings.model_fields["auth_session_ttl_seconds"].default == 30 * 24 * 60 * 60
    configured = settings.model_copy(update={"auth_session_ttl_seconds": 120})
    sessions = service(repository, cache, configured)
    issued = sessions.create(uuid4(), user_agent="session-test")
    repository.create.assert_called_once_with(issued.session)
    cache.set.assert_not_called()
    assert issued.session.expires_at == NOW + timedelta(seconds=120)
    assert issued.session.token_hash == hash_token(issued.token)
    assert issued.token not in repr(issued)
    repository.get_by_token_hash.return_value = issued.session
    assert sessions.validate(issued.token) == issued.session
    assert sessions.validate(issued.token) == issued.session
    repository.get_by_token_hash.assert_called_once_with(issued.session.token_hash)
    cache.set.assert_called_once_with(issued.session)
    with pytest.raises(ValidationError):
        Settings.model_validate(settings.model_dump() | {"auth_session_ttl_seconds": 0})


@pytest.mark.parametrize("token", ["", "x" * 42, "x" * 44, "!" * 43])
def test_invalid_token_format(settings: Settings, cache: Mock, token: str) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    with pytest.raises(InvalidSession):
        service(repository, cache, settings).validate(token)
    cache.get.assert_not_called()
    repository.get_by_token_hash.assert_not_called()


@pytest.mark.parametrize("state", ["unknown", "expired", "revoked"])
def test_reject_invalid_sessions(settings: Settings, cache: Mock, state: str) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    sessions = service(repository, cache, settings)
    issued = sessions.create(uuid4())
    invalid = None
    if state == "expired":
        invalid = replace(
            issued.session,
            created_at=NOW - timedelta(days=2),
            last_seen_at=NOW - timedelta(days=2),
            expires_at=NOW,
        )
    elif state == "revoked":
        invalid = replace(issued.session, revoked_at=NOW)
    repository.get_by_token_hash.return_value = invalid
    cache.get.side_effect = None
    cache.get.return_value = invalid
    with pytest.raises(InvalidSession):
        sessions.validate(issued.token)
    cache.set.assert_not_called()


def test_cache_mismatch_and_outage_fall_back(settings: Settings, cache: Mock) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    sessions = service(repository, cache, settings)
    issued = sessions.create(uuid4())
    repository.get_by_token_hash.return_value = issued.session
    cache.get.side_effect = None
    cache.get.return_value = replace(issued.session, token_hash="0" * 64, user_id=uuid4())
    assert sessions.validate(issued.token) == issued.session
    cache.get.side_effect = SessionCacheUnavailable("Session cache is unavailable.")
    cache.set.side_effect = SessionCacheUnavailable("Session cache is unavailable.")
    assert sessions.validate(issued.token) == issued.session
    assert repository.get_by_token_hash.call_count == 2


def test_revocation_invalidates_cache(settings: Settings, cache: Mock) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    sessions = service(repository, cache, settings)
    issued = sessions.create(uuid4())
    cache.set(issued.session)
    repository.revoke.return_value = issued.session.token_hash
    sessions.revoke(issued.session.id)
    cache.delete.assert_called_once_with(issued.session.token_hash)
    assert cache.get(issued.session.token_hash) is None
    repository.revoke.return_value = None
    sessions.revoke(uuid4())
    assert cache.delete.call_count == 1
    other = sessions.create(issued.session.user_id)
    for item in (issued, other):
        cache.set(item.session)
    repository.revoke_all_for_user.return_value = [
        issued.session.token_hash,
        other.session.token_hash,
    ]
    sessions.revoke_all_for_user(issued.session.user_id)
    assert cache.get(issued.session.token_hash) is None
    assert cache.get(other.session.token_hash) is None
    cache.delete.assert_called_with(issued.session.token_hash, other.session.token_hash)
    cache.delete.side_effect = SessionCacheUnavailable("Session cache is unavailable.")
    with pytest.raises(SessionCacheUnavailable):
        sessions.revoke_all_for_user(issued.session.user_id)


def test_redis_serialization_and_invalid_data(settings: Settings, cache: Mock) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    issued = service(repository, cache, settings).create(
        uuid4(), user_agent="cache-test", ip_address=ip_address("2001:db8::1")
    )
    client = create_autospec(Redis, instance=True)
    redis_cache = RedisSessionCache(client, now=lambda: NOW)
    redis_cache.set(issued.session)
    key, payload = client.set.call_args.args
    assert issued.token.encode() not in payload
    assert client.set.call_args.kwargs["pxat"] == int(issued.session.expires_at.timestamp() * 1000)
    client.get.return_value = payload
    assert redis_cache.get(issued.session.token_hash) == issued.session
    assert redis_cache.get("0" * 64) is None
    for invalid in (None, b"not-json", b"{}", b'{"id":"invalid"}'):
        client.get.return_value = invalid
        assert redis_cache.get(issued.session.token_hash) is None
    client.get.return_value = payload
    redis_cache.now = lambda: issued.session.expires_at
    assert redis_cache.get(issued.session.token_hash) is None
    redis_cache.set(issued.session)
    client.delete.assert_called_with(key)
    redis_cache.now = lambda: NOW
    redis_cache.set(replace(issued.session, revoked_at=NOW))
    client.delete.assert_called_with(key)
    client.delete.reset_mock()
    redis_cache.delete()
    client.delete.assert_not_called()


@pytest.mark.parametrize("operation", ["get", "set", "delete"])
def test_redis_errors_are_sanitized(settings: Settings, cache: Mock, operation: str) -> None:
    repository = create_autospec(SessionRepository, instance=True)
    issued = service(repository, cache, settings).create(uuid4())
    client = create_autospec(Redis, instance=True)
    getattr(client, operation).side_effect = RedisConnectionError("secret connection details")
    redis_cache = RedisSessionCache(client, now=lambda: NOW)
    with pytest.raises(SessionCacheUnavailable) as error:
        if operation == "set":
            redis_cache.set(issued.session)
        elif operation == "get":
            redis_cache.get(issued.session.token_hash)
        else:
            redis_cache.delete(issued.session.token_hash)
    assert "secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_live_redis_cache(settings: Settings, cache: Mock) -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run Redis integration checks.")
    client = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    redis_cache = RedisSessionCache(client)
    repository = create_autospec(SessionRepository, instance=True)
    sessions = service(repository, cache, settings)
    issued = [sessions.create(uuid4()), sessions.create(uuid4())]
    hashes = [item.session.token_hash for item in issued]
    keys = [f"ukladen:auth:session:{token_hash}" for token_hash in hashes]
    try:
        for item, key in zip(issued, keys, strict=True):
            assert redis_cache.get(item.session.token_hash) is None
            redis_cache.set(item.session)
            assert redis_cache.get(item.session.token_hash) == item.session
            ttl = client.pttl(key)
            assert isinstance(ttl, int) and 0 < ttl <= settings.auth_session_ttl_seconds * 1000
        client.set(keys[0], b"not-json", ex=60)
        assert redis_cache.get(hashes[0]) is None
        redis_cache.delete(*hashes)
        assert all(redis_cache.get(token_hash) is None for token_hash in hashes)
    finally:
        client.delete(*keys)
        client.close()


@pytest.fixture
def concurrent_engine() -> Iterator[Engine]:
    url = os.environ.get("AUTH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_DATABASE_URL to run PostgreSQL concurrency checks.")
    schema = f"auth_session_test_{uuid4().hex}"
    engine = create_engine(
        url,
        connect_args={
            "connect_timeout": 3,
            "options": f"-csearch_path={schema} -clock_timeout=3s -cstatement_timeout=5s",
        },
    )
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.dialect.default_schema_name = schema
            command.upgrade(migration_config(connection), "head")
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        engine.dispose()


def test_row_lock_orders_cache_fill_and_revocation(
    concurrent_engine: Engine, settings: Settings, cache: Mock
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="lock@example.com")
        database.add(user)
        database.flush()
        issued = service(SqlAlchemySessionRepository(database), cache, settings).create(user.id)
    with Session(concurrent_engine) as reader, Session(concurrent_engine) as writer:
        read_service = service(SqlAlchemySessionRepository(reader), cache, settings)
        write_service = service(SqlAlchemySessionRepository(writer), cache, settings)
        assert read_service.validate(issued.token) == issued.session
        with pytest.raises(OperationalError, match="lock timeout"), writer.begin():
            writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
            write_service.revoke(issued.session.id)
        assert cache.get(issued.session.token_hash) == issued.session
        reader.commit()
        with writer.begin():
            write_service.revoke(issued.session.id)
        assert cache.get(issued.session.token_hash) is None
        with pytest.raises(InvalidSession):
            read_service.validate(issued.token)
        cache.set.assert_called_once_with(issued.session)


def test_failed_invalidation_rolls_back_revocation(
    concurrent_engine: Engine, settings: Settings, cache: Mock
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="rollback@example.com")
        database.add(user)
        database.flush()
        sessions = service(SqlAlchemySessionRepository(database), cache, settings)
        issued = sessions.create(user.id)
    cache.set(issued.session)
    cache.delete.side_effect = SessionCacheUnavailable("Session cache is unavailable.")
    with Session(concurrent_engine) as database:
        sessions = service(SqlAlchemySessionRepository(database), cache, settings)
        with pytest.raises(SessionCacheUnavailable), database.begin():
            sessions.revoke(issued.session.id)
        stored = SqlAlchemySessionRepository(database).get_by_token_hash(issued.session.token_hash)
        assert stored is not None and stored.revoked_at is None
        stored.require_active(NOW)
        assert cache.get(issued.session.token_hash) == stored


def test_revocation_lock_prevents_stale_cache_fill(
    concurrent_engine: Engine, settings: Settings, cache: Mock
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        user = UserModel(email="revocation-lock@example.com")
        database.add(user)
        database.flush()
        issued = service(SqlAlchemySessionRepository(database), cache, settings).create(user.id)
    with Session(concurrent_engine) as writer, Session(concurrent_engine) as reader:
        write_service = service(SqlAlchemySessionRepository(writer), cache, settings)
        read_service = service(SqlAlchemySessionRepository(reader), cache, settings)
        write_service.revoke(issued.session.id)
        with pytest.raises(OperationalError, match="lock timeout"), reader.begin():
            reader.execute(text("SET LOCAL lock_timeout = '100ms'"))
            read_service.validate(issued.token)
        cache.set.assert_not_called()
        writer.commit()
        with pytest.raises(InvalidSession):
            read_service.validate(issued.token)
        cache.set.assert_not_called()
