from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, delete, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.materials.application.ports import MaterialStorage
from app.modules.materials.application.service import MaterialService
from app.modules.materials.domain.materials import MAX_FILE_BYTES, StorageQuotaExceeded
from app.modules.materials.infrastructure.orm import MaterialModel, MaterialObjectModel
from app.modules.materials.infrastructure.repository import SqlAlchemyMaterialRepository
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.relations.infrastructure.orm import PageMaterialLinkModel
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def material_service(session: Session) -> MaterialService:
    return MaterialService(
        SqlAlchemyMaterialRepository(session),
        SqlAlchemyUserAuthentication(session),
        Mock(spec=MaterialStorage),
    )


def test_constraints_owner_links_and_cleanup_ledger(database_connection: Connection) -> None:
    config = migration_config(database_connection)
    command.check(config)
    owner, other, page_id = uuid4(), uuid4(), uuid4()
    with Session(database_connection, join_transaction_mode="create_savepoint") as session:
        session.add_all(
            [
                UserModel(id=owner, email="materials@example.com"),
                UserModel(id=other, email="other@example.com"),
            ]
        )
        session.flush()
        session.add(PageModel(id=page_id, user_id=owner, title="Independent page"))
        service = material_service(session)
        material = service.create_upload(owner, "Lecture.txt", 100)
        assert service.get(owner, material.id) == material
        assert service.list(other) == []
        assert service.usage(owner) == (100, 1)
        service.lifecycle(owner, material.id, 1, restore=False)
        assert service.usage(owner) == (100, 1)
        for changes in (
            {"size_bytes": 0},
            {"size_bytes": MAX_FILE_BYTES + 1},
            {"version": 0},
            {"status": "unknown"},
            {"status": "processing"},
            {"attempts": 4},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                row = session.get(MaterialModel, material.id)
                assert row is not None
                session.execute(
                    insert(MaterialModel).values(
                        **(
                            {
                                column.name: getattr(row, column.name)
                                for column in MaterialModel.__table__.columns
                            }
                            | {"id": uuid4()}
                            | changes
                        )
                    )
                )
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                PageMaterialLinkModel(page_id=page_id, material_id=material.id, user_id=other)
            )
            session.flush()
        session.add(PageMaterialLinkModel(page_id=page_id, material_id=material.id, user_id=owner))
        session.flush()
        session.execute(delete(UserModel).where(UserModel.id == owner))
        assert session.scalar(select(MaterialModel.id)) is None
        ledger = session.scalar(select(MaterialObjectModel))
        assert (
            ledger is not None
            and ledger.material_id is None
            and ledger.storage_key == material.storage_key
        )
        session.commit()
    with pytest.raises(RuntimeError, match="must be preserved"):
        command.downgrade(config, "0018_reminders_notifications")
    database_connection.execute(delete(MaterialObjectModel))
    command.downgrade(config, "0018_reminders_notifications")
    assert "materials" not in inspect(database_connection).get_table_names()
    command.upgrade(config, "head")
    command.check(config)


def test_concurrent_upload_reservations_cannot_exceed_quota(concurrent_engine: Engine) -> None:
    owner = uuid4()
    with Session(concurrent_engine) as session, session.begin():
        session.add(UserModel(id=owner, email="quota@example.com"))
        session.flush()
        service = material_service(session)
        for _ in range(40):
            service.create_upload(owner, "reserved.txt", MAX_FILE_BYTES)

    def reserve(_: int) -> bool:
        try:
            with Session(concurrent_engine) as session, session.begin():
                material_service(session).create_upload(owner, "race.txt", 16 * 1024 * 1024)
            return True
        except StorageQuotaExceeded:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [False, True]
    with Session(concurrent_engine) as session:
        assert material_service(session).usage(owner) == ((1000 + 16) * 1024 * 1024, 41)
