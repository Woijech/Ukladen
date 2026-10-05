import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from typing import cast
from unittest.mock import Mock, create_autospec
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, event, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import CSRF_COOKIE, SESSION_COOKIE, browser_login, csrf_headers, seed_user
from test_auth_http import browser_settings as browser_settings
from test_auth_http import live_client as live_client
from test_auth_login import password_hash as password_hash
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_users_avatar import image_bytes
from test_users_profile_http import snapshot

from alembic import command
from app.modules.auth.infrastructure.token_service import generate_token
from app.modules.auth.presentation.dependencies import Database
from app.modules.users.application.avatar import AvatarService
from app.modules.users.application.ports import AvatarStorage, AvatarStorageUnavailable
from app.modules.users.domain.avatar import MAX_AVATAR_BYTES
from app.modules.users.domain.profile import UserProfile
from app.modules.users.infrastructure.avatar_image import PillowAvatarImageProcessor
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyProfileRepository
from app.modules.users.presentation.avatar import get_avatars

URL = "/api/v1/users/me/avatar"


@pytest.fixture
def avatar_storage() -> Mock:
    storage = create_autospec(AvatarStorage, instance=True)
    objects: dict[str, bytes] = {}
    storage.put.side_effect = lambda key, content: objects.__setitem__(key, content)
    storage.get.side_effect = objects.get
    storage.delete.side_effect = lambda key: objects.pop(key, None)
    storage.objects = objects
    return storage


@pytest.fixture
def avatar_client(live_client: TestClient, avatar_storage: Mock) -> TestClient:
    application = cast(FastAPI, live_client.app)

    def avatars(database: Database) -> AvatarService:
        return AvatarService(
            SqlAlchemyProfileRepository(database), avatar_storage, PillowAvatarImageProcessor()
        )

    application.dependency_overrides[get_avatars] = avatars
    return live_client


def test_avatar_upload_read_replace_remove_and_ownership(
    avatar_client: TestClient, avatar_storage: Mock, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    seed_user(concurrent_engine, "other@example.com", password_hash)
    token = browser_login(avatar_client)
    before = snapshot(concurrent_engine)
    profile = avatar_client.get("/api/v1/users/me").json()
    assert profile["avatar_url"] is None and "avatar_key" not in profile
    assert avatar_client.get(URL).status_code == 404
    for format, color, content_type in (
        ("JPEG", "red", "image/jpeg"),
        ("WEBP", "blue", "image/webp"),
    ):
        old_keys = set(avatar_storage.objects)
        response = avatar_client.put(
            URL,
            headers=csrf_headers(avatar_client) | {"Content-Type": content_type},
            content=image_bytes(format, color=color),
        )
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        result = response.json()
        assert result["avatar_url"] == URL and "avatar_key" not in result
        assert avatar_client.get("/api/v1/users/me").json() == result
        assert {k: v for k, v in result.items() if k not in {"updated_at", "avatar_url"}} == {
            k: v for k, v in profile.items() if k not in {"updated_at", "avatar_url"}
        }
        with Session(concurrent_engine) as database:
            user = database.get(UserModel, UUID(profile["id"]))
            assert user and user.avatar_key
            assert user.avatar_key.startswith(f"avatars/{user.id}/")
            assert set(avatar_storage.objects) == {user.avatar_key}
        assert not old_keys.intersection(avatar_storage.objects)
        response = avatar_client.get(URL)
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    # Profile patches cannot supply storage keys and cannot erase the existing avatar.
    headers = csrf_headers(avatar_client)
    assert (
        avatar_client.patch(
            "/api/v1/users/me", headers=headers, json={"avatar_key": "foreign-key"}
        ).status_code
        == 422
    )
    assert (
        avatar_client.patch("/api/v1/users/me", headers=headers, json={"locale": "en"}).json()[
            "avatar_url"
        ]
        == URL
    )
    after = snapshot(concurrent_engine)
    for table in ("auth_credentials", "auth_identities", "auth_sessions", "auth_one_time_tokens"):
        assert after[table] == before[table]
    other_before = next(row for row in before["users"] if row["email"] == "other@example.com")
    assert next(row for row in after["users"] if row["id"] == other_before["id"]) == other_before
    browser_login(avatar_client, "other@example.com")
    assert avatar_client.get(URL).status_code == 404
    assert avatar_client.get("/api/v1/users/me").json()["avatar_url"] is None
    assert avatar_client.delete(URL, headers=csrf_headers(avatar_client)).status_code == 204
    assert len(avatar_storage.objects) == 1
    avatar_client.cookies.clear()
    avatar_client.cookies.set(SESSION_COOKIE, token)
    response = avatar_client.delete(URL, headers=csrf_headers(avatar_client))
    assert response.status_code == 204 and response.headers["cache-control"] == "no-store"
    assert not avatar_storage.objects
    assert avatar_client.get(URL).status_code == 404
    final = snapshot(concurrent_engine)
    assert avatar_client.delete(URL, headers=csrf_headers(avatar_client)).status_code == 204
    assert snapshot(concurrent_engine) == final


@pytest.mark.parametrize("method", ["put", "get", "delete"])
def test_avatar_requires_authentication(
    avatar_client: TestClient, avatar_storage: Mock, method: str
) -> None:
    response = avatar_client.request(
        method,
        URL,
        headers=csrf_headers(avatar_client),
        content=image_bytes() if method == "put" else None,
    )
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    avatar_storage.put.assert_not_called()
    avatar_storage.get.assert_not_called()
    avatar_storage.delete.assert_not_called()


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("failure", ["origin", "foreign_origin", "header", "cookie", "mismatch"])
def test_avatar_requires_csrf(
    avatar_client: TestClient,
    avatar_storage: Mock,
    concurrent_engine: Engine,
    password_hash: str,
    method: str,
    failure: str,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(avatar_client)
    headers = csrf_headers(avatar_client) | {"Content-Type": "image/png"}
    if failure == "origin":
        headers.pop("Origin")
    elif failure == "foreign_origin":
        headers["Origin"] = "https://attacker.example"
    elif failure == "header":
        headers.pop("X-CSRF-Token")
    elif failure == "cookie":
        avatar_client.cookies.delete(CSRF_COOKIE)
    else:
        headers["X-CSRF-Token"] = generate_token()
    response = avatar_client.request(
        method, URL, headers=headers, content=image_bytes() if method == "put" else None
    )
    assert response.status_code == 403 and response.headers["cache-control"] == "no-store"
    avatar_storage.put.assert_not_called()
    avatar_storage.delete.assert_not_called()


@pytest.mark.parametrize(
    "case, status",
    [
        ("oversized", 413),
        ("chunked", 413),
        ("pixels", 413),
        ("malformed", 422),
        ("mismatch", 422),
        ("svg", 422),
    ],
)
def test_avatar_validation_has_no_side_effects(
    avatar_client: TestClient,
    avatar_storage: Mock,
    concurrent_engine: Engine,
    password_hash: str,
    case: str,
    status: int,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(avatar_client)
    headers = csrf_headers(avatar_client) | {"Content-Type": "image/png"}
    content = image_bytes()
    if case in {"oversized", "chunked"}:
        content = b"x" * (MAX_AVATAR_BYTES + 1)
    elif case == "pixels":
        content = image_bytes(size=(3000, 1500))
    elif case == "malformed":
        content = b"private-malformed-data"
    elif case == "mismatch":
        headers["Content-Type"] = "image/jpeg"
    else:
        headers["Content-Type"] = "image/svg+xml"
        content = b"<svg>private-data</svg>"
    before = snapshot(concurrent_engine)
    response = avatar_client.put(
        URL,
        headers=headers,
        content=iter((content[:100], content[100:])) if case == "chunked" else content,
    )
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    assert "private" not in response.text and snapshot(concurrent_engine) == before
    avatar_storage.put.assert_not_called()
    avatar_storage.delete.assert_not_called()


@pytest.mark.parametrize("failure", ["storage", "write", "commit", "cleanup"])
def test_avatar_failure_preserves_previous_image(
    avatar_client: TestClient,
    avatar_storage: Mock,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(avatar_client)
    headers = csrf_headers(avatar_client) | {"Content-Type": "image/png"}
    assert avatar_client.put(URL, headers=headers, content=image_bytes()).status_code == 200
    before = snapshot(concurrent_engine)
    old_objects = dict(avatar_storage.objects)
    old_key = next(iter(old_objects))
    original = SqlAlchemyProfileRepository.update_avatar

    def fail_write(self: SqlAlchemyProfileRepository, user_id: UUID, key: str | None) -> None:
        original(self, user_id, key)
        raise SQLAlchemyError("private-write-details")

    def fail_commit(database: Session) -> None:
        key = database.scalar(select(UserModel.avatar_key))
        if key is not None and key != old_key:
            raise SQLAlchemyError("private-commit-details")

    if failure == "storage":
        avatar_storage.put.side_effect = AvatarStorageUnavailable("private-storage-details")
    elif failure == "write":
        monkeypatch.setattr(SqlAlchemyProfileRepository, "update_avatar", fail_write)
    elif failure == "commit":
        event.listen(Session, "before_commit", fail_commit)
    else:
        monkeypatch.setattr(
            logging.getLogger("app.modules.users.application.avatar"), "disabled", False
        )
        avatar_storage.delete.side_effect = AvatarStorageUnavailable("private-cleanup-details")
    try:
        response = avatar_client.put(URL, headers=headers, content=image_bytes(color="blue"))
    finally:
        if failure == "commit":
            event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == (200 if failure == "cleanup" else 503)
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text and "private" not in caplog.text
    if failure == "cleanup":
        assert len(avatar_storage.objects) == 2 and "Avatar cleanup failed." in caplog.text
        assert avatar_client.get(URL).content != old_objects[old_key]
    else:
        assert snapshot(concurrent_engine) == before and avatar_storage.objects == old_objects
        assert avatar_client.get(URL).content == old_objects[old_key]


def test_avatar_migration_round_trip_preserves_existing_data(
    database_connection: Connection,
) -> None:
    config = migration_config(database_connection)
    command.downgrade(config, "0003_users_profile")
    user_id = uuid4()
    database_connection.execute(
        insert(UserModel).values(
            id=user_id,
            email="migration@example.com",
            display_name="Alex",
            timezone="Europe/Minsk",
            locale="en",
        )
    )
    before = dict(
        database_connection.execute(
            select(
                UserModel.__table__.c.id,
                UserModel.__table__.c.email,
                UserModel.__table__.c.display_name,
                UserModel.__table__.c.updated_at,
            )
        )
        .mappings()
        .one()
    )
    command.upgrade(config, "head")
    assert (
        database_connection.scalar(select(UserModel.avatar_key).where(UserModel.id == user_id))
        is None
    )
    key = f"avatars/{user_id}/{uuid4().hex}.png"
    database_connection.execute(
        update(UserModel).where(UserModel.id == user_id).values(avatar_key=key)
    )
    with pytest.raises(IntegrityError), database_connection.begin_nested():
        database_connection.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(avatar_key=f"avatars/{uuid4()}/{uuid4().hex}.png")
        )
    command.check(config)
    command.downgrade(config, "0003_users_profile")
    assert "avatar_key" not in {
        column["name"] for column in inspect(database_connection).get_columns("users")
    }
    after = dict(
        database_connection.execute(
            select(
                UserModel.__table__.c.id,
                UserModel.__table__.c.email,
                UserModel.__table__.c.display_name,
                UserModel.__table__.c.updated_at,
            )
        )
        .mappings()
        .one()
    )
    assert before == after
    command.upgrade(config, "head")
    command.check(config)


def test_avatar_and_profile_concurrent_updates_preserve_both(
    concurrent_engine: Engine, avatar_storage: Mock
) -> None:
    seed_user(concurrent_engine, "concurrent@example.com", "test-hash")
    with Session(concurrent_engine) as database:
        user_id = database.scalar(select(UserModel.id))
        assert user_id
    attempted = Event()

    def update_profile() -> None:
        with Session(concurrent_engine) as database, database.begin():
            attempted.set()
            SqlAlchemyProfileRepository(database).update_active(user_id, {"locale": "en"})

    with Session(concurrent_engine) as database, ThreadPoolExecutor(max_workers=1) as executor:
        avatars = AvatarService(
            SqlAlchemyProfileRepository(database), avatar_storage, PillowAvatarImageProcessor()
        )
        prepared = avatars.prepare(user_id, image_bytes(), "image/png")
        avatars.replace(user_id, prepared)
        future = executor.submit(update_profile)
        assert attempted.wait(1)
        try:
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        finally:
            database.commit()
        future.result(timeout=3)
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, user_id)
        assert user and user.locale == "en" and user.avatar_key == prepared.key


@pytest.mark.parametrize("method", ["put", "get", "delete"])
@pytest.mark.parametrize("state", ["invalid", "revoked", "disabled"])
def test_avatar_rejects_invalid_sessions_and_disabled_users(
    avatar_client: TestClient,
    avatar_storage: Mock,
    concurrent_engine: Engine,
    password_hash: str,
    method: str,
    state: str,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    token = browser_login(avatar_client)
    headers = csrf_headers(avatar_client) | {"Content-Type": "image/png"}
    assert avatar_client.put(URL, headers=headers, content=image_bytes()).status_code == 200
    if state == "revoked":
        assert avatar_client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        avatar_client.cookies.set(SESSION_COOKIE, token)
    elif state == "invalid":
        avatar_client.cookies.clear()
        avatar_client.cookies.set(SESSION_COOKIE, "invalid")
    else:
        with Session(concurrent_engine) as database, database.begin():
            database.execute(update(UserModel).values(status="disabled"))
    before = snapshot(concurrent_engine)
    objects = dict(avatar_storage.objects)
    avatar_storage.reset_mock()
    response = avatar_client.request(
        method,
        URL,
        headers=csrf_headers(avatar_client) | {"Content-Type": "image/png"},
        content=image_bytes() if method == "put" else None,
    )
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    assert snapshot(concurrent_engine) == before and avatar_storage.objects == objects
    avatar_storage.put.assert_not_called()
    avatar_storage.get.assert_not_called()
    avatar_storage.delete.assert_not_called()


def test_avatar_delete_commit_failure_and_download_storage_failure(
    avatar_client: TestClient, avatar_storage: Mock, concurrent_engine: Engine, password_hash: str
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(avatar_client)
    headers = csrf_headers(avatar_client) | {"Content-Type": "image/png"}
    assert avatar_client.put(URL, headers=headers, content=image_bytes()).status_code == 200
    before = snapshot(concurrent_engine)
    objects = dict(avatar_storage.objects)

    def fail_commit(database: Session) -> None:
        if database.scalar(select(UserModel.avatar_key)) is None:
            raise SQLAlchemyError("private-commit-details")

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = avatar_client.delete(URL, headers=headers)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 503
    assert snapshot(concurrent_engine) == before and avatar_storage.objects == objects
    avatar_storage.get.side_effect = AvatarStorageUnavailable("private-storage-details")
    response = avatar_client.get(URL)
    assert response.status_code == 503 and "private" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(concurrent_engine) == before and avatar_storage.objects == objects


def test_ambiguous_commit_keeps_the_committed_avatar(
    avatar_client: TestClient,
    avatar_storage: Mock,
    concurrent_engine: Engine,
    password_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(avatar_client)
    headers = csrf_headers(avatar_client) | {"Content-Type": "image/png"}

    # Model a committed transaction whose acknowledgement was lost; fire only on the avatar write.
    def fail_after_commit(database: Session) -> None:
        if database.info.pop("avatar_write", False):
            raise SQLAlchemyError("private-lost-acknowledgement")

    original = SqlAlchemyProfileRepository.update_avatar

    def mark_update(
        self: SqlAlchemyProfileRepository, user_id: UUID, key: str | None
    ) -> UserProfile | None:
        result = original(self, user_id, key)
        self.session.info["avatar_write"] = True
        return result

    event.listen(Session, "after_commit", fail_after_commit)
    monkeypatch.setattr(SqlAlchemyProfileRepository, "update_avatar", mark_update)
    try:
        response = avatar_client.put(URL, headers=headers, content=image_bytes())
    finally:
        event.remove(Session, "after_commit", fail_after_commit)
    assert response.status_code == 503 and "private" not in response.text
    with Session(concurrent_engine) as database:
        key = database.scalar(select(UserModel.avatar_key))
        assert key and key in avatar_storage.objects
    assert avatar_client.get(URL).status_code == 200
    avatar_storage.delete.assert_not_called()


def test_concurrent_avatar_replacements_remove_only_previous_objects(
    concurrent_engine: Engine, avatar_storage: Mock
) -> None:
    seed_user(concurrent_engine, "concurrent@example.com", "test-hash")
    with Session(concurrent_engine) as database:
        user_id = database.scalar(select(UserModel.id))
        assert user_id
    attempted = Event()

    def second_replace() -> str:
        with Session(concurrent_engine) as database:
            avatars = AvatarService(
                SqlAlchemyProfileRepository(database), avatar_storage, PillowAvatarImageProcessor()
            )
            prepared = avatars.prepare(user_id, image_bytes(color="blue"), "image/png")
            with database.begin():
                attempted.set()
                change = avatars.replace(user_id, prepared)
            avatars.cleanup(change.previous_key)
            return prepared.key

    with Session(concurrent_engine) as database, ThreadPoolExecutor(max_workers=1) as executor:
        avatars = AvatarService(
            SqlAlchemyProfileRepository(database), avatar_storage, PillowAvatarImageProcessor()
        )
        prepared = avatars.prepare(user_id, image_bytes(), "image/png")
        change = avatars.replace(user_id, prepared)
        future = executor.submit(second_replace)
        assert attempted.wait(1)
        try:
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
        finally:
            database.commit()
        avatars.cleanup(change.previous_key)
        final_key = future.result(timeout=3)
    with Session(concurrent_engine) as database:
        assert database.scalar(select(UserModel.avatar_key)) == final_key
    assert set(avatar_storage.objects) == {final_key}
