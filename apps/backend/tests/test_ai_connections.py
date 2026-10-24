import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_ai_persistence import ai_database as ai_database
from test_ai_persistence import migration_config, seed

from alembic import command
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.domain.connections import (
    ConnectionLimited,
    ConnectionUnavailable,
    PersonalConnection,
)
from app.modules.ai.domain.state import AiNotFound
from app.modules.ai.infrastructure.connections import FileConnectionConfiguration
from app.modules.ai.infrastructure.orm import ConversationModel, PersonalConnectionModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository

KEY = "synthetic-private-api-credential"


@pytest.fixture
def configuration(tmp_path: Path) -> FileConnectionConfiguration:
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "flash",
                        "version": 1,
                        "name": "Synthetic Flash",
                        "model": "deepseek/deepseek-v4.1-flash",
                        "enabled": True,
                        "public": True,
                        "operator_key_file": "operator.key",
                        "tools": True,
                    }
                ]
            }
        )
    )
    (tmp_path / "operator.key").write_text(KEY)
    (tmp_path / "operator.key").chmod(0o600)
    write_keyring(tmp_path, "v1", {"v1": os.urandom(32)})
    return FileConnectionConfiguration(tmp_path / "catalog.json")


def write_keyring(path: Path, active: str, keys: dict[str, bytes]) -> None:
    target = path / "master-keys.json"
    target.write_text(
        json.dumps(
            {
                "active": active,
                "keys": {key: base64.b64encode(value).decode() for key, value in keys.items()},
            }
        )
    )
    target.chmod(0o600)


def connection(configuration: FileConnectionConfiguration) -> PersonalConnection:
    owner, identifier = uuid4(), uuid4()
    key_id, encrypted = configuration.encrypt(owner, identifier, KEY)
    return PersonalConnection(
        id=identifier,
        user_id=owner,
        label="Private account",
        created_at=datetime.now(UTC),
        encrypted_key=encrypted,
        encryption_key_id=key_id,
    )


def test_cipher_authenticates_owner_connection_and_ciphertext_and_masks_repr(configuration):
    stored = connection(configuration)
    assert stored.encrypted_key is not None
    assert configuration.decrypt(stored) == KEY
    assert KEY.encode() not in stored.encrypted_key and KEY not in repr(stored)
    again = configuration.encrypt(stored.user_id, stored.id, KEY)[1]
    assert again != stored.encrypted_key
    for changed in (
        replace(stored, user_id=uuid4()),
        replace(stored, id=uuid4()),
        replace(stored, encrypted_key=stored.encrypted_key[:-1] + b"!"),
        replace(stored, encryption_key_id="missing"),
        replace(
            stored, disconnected_at=datetime.now(UTC), encrypted_key=None, encryption_key_id=None
        ),
    ):
        with pytest.raises(ConnectionUnavailable):
            configuration.decrypt(changed)


def test_rotation_preserves_old_reads_until_reencrypted_and_old_key_removal(configuration):
    stored = connection(configuration)
    path = configuration.path.parent
    previous = json.loads((path / "master-keys.json").read_text())
    old = base64.b64decode(previous["keys"]["v1"])
    new = os.urandom(32)
    write_keyring(path, "v2", {"v1": old, "v2": new})
    assert configuration.decrypt(stored) == KEY
    key_id, encrypted = configuration.encrypt(
        stored.user_id, stored.id, configuration.decrypt(stored)
    )
    rotated = replace(stored, encrypted_key=encrypted, encryption_key_id=key_id)
    assert key_id == "v2" and configuration.decrypt(rotated) == KEY
    write_keyring(path, "v2", {"v2": new})
    assert configuration.decrypt(rotated) == KEY
    with pytest.raises(ConnectionUnavailable):
        configuration.decrypt(stored)


def test_catalog_is_allowlisted_versioned_safe_and_reloaded(configuration):
    owner, outsider = uuid4(), uuid4()
    data = json.loads(configuration.path.read_text())
    data["entries"][0].update(public=False, allowed_user_ids=[str(owner)])
    configuration.path.write_text(json.dumps(data))
    assert configuration.offerings(outsider) == []
    with pytest.raises(AiNotFound):
        configuration.offering(outsider, "flash")
    public = configuration.offerings(owner)[0].model_dump()
    assert "operator_key_file" not in public and "allowed_user_ids" not in public
    assert configuration.operator_key("flash") == KEY
    data["entries"][0]["enabled"] = False
    configuration.path.write_text(json.dumps(data))
    with pytest.raises(AiNotFound):
        configuration.offering(owner, "flash")


def test_missing_corrupt_or_readable_secret_fails_closed(configuration):
    path = configuration.path.parent / "operator.key"
    path.chmod(0o644)
    with pytest.raises(ConnectionUnavailable):
        configuration.operator_key("flash")
    path.unlink()
    path.symlink_to(configuration.path)
    with pytest.raises(ConnectionUnavailable):
        configuration.operator_key("flash")
    (configuration.path.parent / "master-keys.json").write_text("broken")
    with pytest.raises(ConnectionUnavailable):
        connection(configuration)


def test_personal_access_never_falls_back_and_disconnection_clears_secret(configuration):
    repository = create_autospec(AiRepository, instance=True)
    stored = connection(configuration)
    repository.get_connection.return_value = stored
    repository.connection_runs.return_value = []
    access = ConnectionAccess(configuration)
    selection, _ = access.select(repository, stored.user_id, "flash", stored.id)
    assert access.check(repository, stored.user_id, selection, datetime.now(UTC))[1] == KEY
    repository.get_connection.return_value = replace(
        stored, disconnected_at=datetime.now(UTC), encrypted_key=None, encryption_key_id=None
    )
    with pytest.raises(ConnectionUnavailable):
        access.check(repository, stored.user_id, selection, datetime.now(UTC))
    repository.get_connection.return_value = stored
    access.disconnect(repository, stored.user_id, stored.id, datetime.now(UTC))
    cleared = repository.save_connection.call_args.args[0]
    assert cleared.encrypted_key is None and cleared.encryption_key_id is None
    assert cleared.disconnected_at is not None
    repository.get_connection.return_value = None
    with pytest.raises(AiNotFound):
        access.select(repository, stored.user_id, "flash", stored.id)


def test_native_encryption_ownership_quota_and_disconnect(ai_database: Engine, configuration):
    chat, outsider = seed(ai_database)
    access = ConnectionAccess(configuration)
    now = datetime.now(UTC)
    with Session(ai_database) as database, database.begin():
        repository = SqlAlchemyAiRepository(database)
        stored = access.create(repository, chat.user_id, "Private account", KEY, now)
        assert stored.encrypted_key is not None
        assert KEY.encode() not in stored.encrypted_key
        assert repository.get_connection(outsider, stored.id) is None
        assert repository.connections(outsider) == []
        repository.admit_connection("synthetic", 1, now)
    with Session(ai_database) as database, database.begin():
        with pytest.raises(ConnectionLimited):
            SqlAlchemyAiRepository(database).admit_connection("synthetic", 1, now)
    with Session(ai_database) as database, database.begin():
        repository = SqlAlchemyAiRepository(database)
        repository.admit_connection("synthetic", 1, now + timedelta(seconds=60))
        access.disconnect(repository, chat.user_id, stored.id, now + timedelta(seconds=1))
    with Session(ai_database) as database:
        row = database.scalar(select(PersonalConnectionModel))
        assert row is not None and row.encrypted_key is None and row.encryption_key_id is None
    with Session(ai_database) as database, database.begin():
        database.add(
            PersonalConnectionModel(
                id=uuid4(),
                user_id=chat.user_id,
                label="Invalid",
                created_at=now,
                encrypted_key=b"secret",
                encryption_key_id="v1",
                disconnected_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            database.flush()


def test_native_shared_quota_serializes_concurrent_admission(ai_database: Engine):
    barrier = Barrier(2)
    now = datetime.now(UTC)

    def admit():
        barrier.wait(timeout=5)
        try:
            with Session(ai_database) as database, database.begin():
                SqlAlchemyAiRepository(database).admit_connection("shared-account", 1, now)
            return True
        except ConnectionLimited:
            return False

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: admit(), range(2)))
    assert sorted(results) == [False, True]
    with Session(ai_database) as database, database.begin():
        SqlAlchemyAiRepository(database).block_connection(
            "shared-account", now + timedelta(hours=1)
        )
    with Session(ai_database) as database, database.begin():
        with pytest.raises(ConnectionLimited):
            SqlAlchemyAiRepository(database).admit_connection(
                "shared-account", 100, now + timedelta(minutes=1)
            )


def test_native_owner_foreign_keys_and_preserving_downgrade(ai_database: Engine, configuration):
    chat, outsider = seed(ai_database)
    now = datetime.now(UTC)
    with Session(ai_database) as database, database.begin():
        stored = ConnectionAccess(configuration).create(
            SqlAlchemyAiRepository(database), chat.user_id, "Private account", KEY, now
        )
    with ai_database.begin() as database:
        with pytest.raises(DBAPIError, match="Cannot downgrade"), database.begin_nested():
            command.downgrade(migration_config(database), "0023_ai_run_receipts")
        assert (
            database.scalar(select(PersonalConnectionModel.encrypted_key)) == stored.encrypted_key
        )
        with pytest.raises(IntegrityError), database.begin_nested():
            database.execute(
                insert(ConversationModel).values(
                    id=uuid4(),
                    user_id=outsider,
                    title="Foreign",
                    created_at=now,
                    next_sequence=1,
                    offering_id="flash",
                    offering_version=1,
                    connection_id=stored.id,
                    provider="openrouter",
                    model="deepseek/deepseek-v4.1-flash",
                )
            )
