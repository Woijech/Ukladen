import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import cast
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from test_auth_http import csrf_headers
from test_logging import capture_json
from test_material_extraction import pdf_bytes
from test_materials_http import BASE, MemoryMaterialStorage, reserve, upload
from test_materials_http import browser_settings as browser_settings
from test_materials_http import calendar_client as calendar_client
from test_materials_http import concurrent_engine as concurrent_engine
from test_materials_http import live_client as live_client
from test_materials_http import material_client as material_client
from test_materials_http import password_hash as password_hash
from test_materials_http import settings as settings
from test_notes_http import create_page
from test_search_http import results

from app.core import config
from app.core.config import Settings
from app.integrations.storage.materials import S3MaterialStorage
from app.modules.materials.application.processing import ExtractionResult
from app.modules.materials.domain.extraction import ExtractedText
from app.modules.materials.domain.materials import MaterialStorageUnavailable
from app.modules.materials.infrastructure.extractor import BoundedDocumentExtractor
from app.modules.materials.infrastructure.jobs import (
    MaterialJobUnavailable,
    dispatch_materials,
    process_material,
    processing_service,
)
from app.modules.materials.infrastructure.orm import MaterialModel, MaterialObjectModel
from app.modules.materials.infrastructure.repository import SqlAlchemyMaterialRepository
from app.modules.search.infrastructure.orm import MaterialSearchDocumentModel
from app.modules.users.infrastructure.orm import UserModel


def storage(client: TestClient) -> MemoryMaterialStorage:
    return cast(FastAPI, client.app).state.material_storage


def process(
    engine: Engine, client: TestClient, material: dict, *, now=None, extractor=None
) -> None:
    process_material(
        sessionmaker(engine),
        storage(client),
        extractor or BoundedDocumentExtractor(),
        UUID(material["id"]),
        **({"now": now} if now is not None else {}),
    )


def state(engine: Engine, material: dict) -> str | None:
    with Session(engine) as database:
        row = database.get(MaterialModel, UUID(material["id"]))
        return row.status if row else None


def test_processing_publishes_once_and_preserves_original(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client, b"quartz lecture material")
    process(concurrent_engine, material_client, material)
    process(concurrent_engine, material_client, material)
    assert state(concurrent_engine, material) == "ready"
    assert results(material_client, "quartz")[0]["id"] == material["id"]
    assert (
        material_client.get(f"{BASE}/{material['id']}/content").content
        == b"quartz lecture material"
    )
    with Session(concurrent_engine) as database:
        assert len(list(database.scalars(select(MaterialSearchDocumentModel)))) == 1


def test_parallel_workers_only_claim_once(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client)
    extractor = Mock()
    extractor.extract.return_value = ExtractedText("lecture")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda _: process(
                    concurrent_engine, material_client, material, extractor=extractor
                ),
                range(2),
            )
        )
    assert extractor.extract.call_count == 1
    assert state(concurrent_engine, material) == "ready"


def test_expired_leases_fence_old_results_and_bound_crash_retries(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client)
    sessions, now = sessionmaker(concurrent_engine), datetime.now(UTC)

    def claim(at):
        with sessions.begin() as database:
            row = database.get(MaterialModel, UUID(material["id"]))
            assert row is not None
            return processing_service(
                database, storage(material_client), BoundedDocumentExtractor(), lambda: at
            ).claim(row.user_id, row.id)

    first = claim(now)
    assert first is not None
    second = claim(now + timedelta(minutes=3))
    assert second is not None and second.lease_token != first.lease_token
    with sessions.begin() as database:
        processing_service(
            database, storage(material_client), BoundedDocumentExtractor(), lambda: now
        ).complete(first, ExtractionResult("obsoletequartz"))
    assert results(material_client, "obsoletequartz") == []
    assert state(concurrent_engine, material) == "processing"
    third = claim(now + timedelta(minutes=6))
    assert third is not None
    assert claim(now + timedelta(minutes=9)) is None
    assert state(concurrent_engine, material) == "failed"
    current = material_client.get(f"{BASE}/{material['id']}").json()
    assert current["error_code"] == "processing_timeout"
    retry = material_client.post(
        f"{BASE}/{material['id']}/retry",
        headers=csrf_headers(material_client),
        json={"expected_version": current["version"]},
    )
    assert retry.status_code == 200
    process(concurrent_engine, material_client, material)
    assert state(concurrent_engine, material) == "ready"


@pytest.mark.parametrize(
    "content,name,mime,error",
    [
        (b"%PDF-invalid", "invalid.pdf", "application/pdf", "invalid_document"),
        (pdf_bytes(None), "scan.pdf", "application/pdf", "no_extractable_text"),
    ],
)
def test_invalid_and_unsearchable_files_remain_downloadable(
    material_client: TestClient, concurrent_engine: Engine, content, name, mime, error
) -> None:
    material = upload(material_client, content, name, mime)
    process(concurrent_engine, material_client, material)
    current = material_client.get(f"{BASE}/{material['id']}").json()
    assert current["error_code"] == error
    assert current["status"] == ("ready" if error == "no_extractable_text" else "failed")
    assert material_client.get(f"{BASE}/{material['id']}/content").content == content


def test_storage_retries_and_transaction_failure_preserve_pending_work(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client)
    with patch.object(storage(material_client), "get", side_effect=MaterialStorageUnavailable()):
        for expected in ("pending", "pending", "failed"):
            process(concurrent_engine, material_client, material)
            assert state(concurrent_engine, material) == expected
    assert material_client.get(f"{BASE}/{material['id']}/content").content == b"study"
    other = upload(material_client)
    original = SqlAlchemyMaterialRepository.save

    def fail(self, value, version):
        if value.status == "ready":
            raise SQLAlchemyError("private-processing-sql")
        return original(self, value, version)

    with patch.object(SqlAlchemyMaterialRepository, "save", fail), pytest.raises(SQLAlchemyError):
        process(concurrent_engine, material_client, other)
    with Session(concurrent_engine) as database:
        assert database.get(MaterialSearchDocumentModel, UUID(other["id"])) is None
    assert state(concurrent_engine, other) == "processing"


def test_trash_during_processing_does_not_publish_index(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client)
    path = f"{BASE}/{material['id']}"
    extractor = Mock()

    def trash(*args):
        current = material_client.get(path).json()
        assert current["status"] == "processing"
        assert (
            material_client.post(
                path + "/trash",
                headers=csrf_headers(material_client),
                json={"expected_version": current["version"]},
            ).status_code
            == 200
        )
        return ExtractedText("privatequartz")

    extractor.extract.side_effect = trash
    process(concurrent_engine, material_client, material, extractor=extractor)
    assert results(material_client, "privatequartz") == []
    current = material_client.get(path).json()
    assert current["status"] == "pending"
    assert (
        material_client.post(
            path + "/restore",
            headers=csrf_headers(material_client),
            json={"expected_version": current["version"]},
        ).status_code
        == 200
    )
    process(concurrent_engine, material_client, material)
    assert state(concurrent_engine, material) == "ready"


def test_cleanup_retries_releases_quota_and_preserves_pages(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material, page = upload(material_client), create_page(material_client)
    process(concurrent_engine, material_client, material)
    assert (
        material_client.put(
            f"/api/v1/relations/pages/{page['id']}/materials/{material['id']}",
            headers=csrf_headers(material_client),
        ).status_code
        == 200
    )
    current = material_client.get(f"{BASE}/{material['id']}").json()
    assert (
        material_client.post(
            f"{BASE}/{material['id']}/trash",
            headers=csrf_headers(material_client),
            json={"expected_version": current["version"]},
        ).status_code
        == 200
    )
    future = datetime.now(UTC) + timedelta(days=31)
    with patch.object(storage(material_client), "delete", side_effect=MaterialStorageUnavailable()):
        with pytest.raises(MaterialJobUnavailable):
            dispatch_materials(
                sessionmaker(concurrent_engine),
                storage(material_client),
                Mock(spec=Celery),
                now=lambda: future,
            )
    assert material_client.get(BASE + "/storage").json()["used_bytes"] == 5
    dispatch_materials(
        sessionmaker(concurrent_engine),
        storage(material_client),
        Mock(spec=Celery),
        now=lambda: future,
    )
    assert state(concurrent_engine, material) is None
    assert storage(material_client).objects == {}
    assert material_client.get(BASE + "/storage").json()["used_bytes"] == 0
    assert material_client.get(f"/api/v1/notes/pages/{page['id']}").status_code == 200
    with Session(concurrent_engine) as database:
        assert database.get(MaterialSearchDocumentModel, UUID(material["id"])) is None


def test_abandoned_upload_and_deleted_owner_objects_are_recovered(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = reserve(material_client)
    with Session(concurrent_engine) as database:
        row = database.get(MaterialModel, UUID(material["id"]))
        assert row is not None
        key = f"materials/{row.user_id}/{row.id}"
    storage(material_client).objects[key] = b"orphaned uploaded bytes"
    dispatch_materials(
        sessionmaker(concurrent_engine),
        storage(material_client),
        Mock(spec=Celery),
        now=lambda: datetime.now(UTC) + timedelta(hours=2),
    )
    assert state(concurrent_engine, material) is None and storage(material_client).objects == {}
    upload(material_client)
    with Session(concurrent_engine) as database, database.begin():
        database.execute(delete(UserModel))
    assert storage(material_client).objects
    dispatch_materials(sessionmaker(concurrent_engine), storage(material_client), Mock(spec=Celery))
    assert storage(material_client).objects == {}
    with Session(concurrent_engine) as database:
        assert list(database.scalars(select(MaterialObjectModel))) == []


def test_broker_gap_retains_pending_work_and_routes_file_queue(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client)
    celery = Mock(spec=Celery)
    celery.send_task.side_effect = ConnectionError("private-broker-detail")
    with capture_json() as output, pytest.raises(MaterialJobUnavailable):
        dispatch_materials(sessionmaker(concurrent_engine), storage(material_client), celery)
    assert "private-broker-detail" not in output.getvalue()
    assert state(concurrent_engine, material) == "pending"
    celery.send_task.side_effect = None
    dispatch_materials(sessionmaker(concurrent_engine), storage(material_client), celery)
    celery.send_task.assert_called_with(
        "materials.process", kwargs={"material_id": material["id"]}, queue="materials"
    )


@pytest.fixture
def material_tasks(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> ModuleType:
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    module = importlib.import_module("app.modules.materials.infrastructure.tasks")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return module


def test_registered_task_executes_and_errors_are_safe(
    material_tasks: ModuleType,
    material_client: TestClient,
    concurrent_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = upload(material_client)
    monkeypatch.setattr(material_tasks, "create_database_engine", lambda _: concurrent_engine)
    monkeypatch.setattr(material_tasks, "S3MaterialStorage", lambda _: storage(material_client))
    material_tasks.celery_app.loader.import_default_modules()
    assert (
        material_tasks.celery_app.conf.beat_schedule["materials-dispatch"]["task"]
        == "materials.dispatch"
    )
    assert material_tasks.process.acks_late and material_tasks.process.reject_on_worker_lost
    assert material_tasks.process.apply(kwargs={"material_id": material["id"]}).successful()
    assert state(concurrent_engine, material) == "ready"
    with capture_json() as output:
        failure = material_tasks.process.apply(kwargs={"material_id": "private-malformed-id"})
        assert failure.failed() and isinstance(failure.result, MaterialJobUnavailable)
        assert material_tasks.process.apply(kwargs={"material_id": None}).failed()
    assert "private-malformed-id" not in output.getvalue()


def test_large_full_text_index_failure_is_bounded(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = upload(material_client)
    sessions, now = sessionmaker(concurrent_engine), datetime.now(UTC)
    with sessions.begin() as database:
        row = database.get(MaterialModel, UUID(material["id"]))
        assert row is not None
        work = processing_service(
            database, storage(material_client), BoundedDocumentExtractor(), lambda: now
        ).claim(row.user_id, row.id)
    assert work is not None
    with sessions.begin() as database:
        service = processing_service(
            database, storage(material_client), BoundedDocumentExtractor(), lambda: now
        )
        service.complete(work, ExtractionResult(" ".join(f"term{i:06d}" for i in range(150000))))
    current = material_client.get(f"{BASE}/{material['id']}").json()
    assert current["status"] == "failed" and current["error_code"] == "document_limit"
    assert material_client.get(f"{BASE}/{material['id']}/content").content == b"study"


def test_native_s3_redis_task_to_search(
    material_tasks: ModuleType,
    material_client: TestClient,
    concurrent_engine: Engine,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint, broker = (
        os.environ.get("AVATAR_TEST_S3_ENDPOINT"),
        os.environ.get("AUTH_TEST_REDIS_URL"),
    )
    if not endpoint or not broker:
        pytest.skip("Set disposable S3 and Redis configuration for native file jobs.")
    objects = S3MaterialStorage(
        Settings.model_validate(
            settings.model_dump()
            | {
                "s3_endpoint": endpoint,
                "s3_access_key": os.environ["AVATAR_TEST_S3_ACCESS_KEY"],
                "s3_secret_key": os.environ["AVATAR_TEST_S3_SECRET_KEY"],
                "s3_bucket": os.environ["AVATAR_TEST_S3_BUCKET"],
            }
        )
    )
    cast(FastAPI, material_client.app).state.material_storage = objects
    monkeypatch.setattr(material_tasks, "create_database_engine", lambda _: concurrent_engine)
    monkeypatch.setattr(material_tasks, "S3MaterialStorage", lambda _: objects)
    monkeypatch.setattr(objects, "close", lambda: None)
    queue = f"ukladen-materials-test-{uuid4().hex}"
    app = Celery("materials-test", broker=broker)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        task_default_queue=queue,
        task_default_exchange=queue,
        task_default_routing_key=queue,
        broker_transport_options={"global_keyprefix": f"{queue}:"},
    )
    redis, key = Redis.from_url(broker), None
    try:
        material = upload(material_client, b"Quartz network search", "network.txt")
        with Session(concurrent_engine) as database:
            row = database.get(MaterialModel, UUID(material["id"]))
            assert row is not None
            key = f"materials/{row.user_id}/{row.id}"
        app.send_task("materials.process", kwargs={"material_id": material["id"]})
        with app.connection_for_read() as connection:
            inbox = connection.SimpleQueue(queue)
            try:
                message = inbox.get(block=False)
                try:
                    args, kwargs, _ = message.payload
                    assert message.headers["task"] == "materials.process"
                    assert material_tasks.process.apply(args=args, kwargs=kwargs).successful()
                    assert material_tasks.process.apply(args=args, kwargs=kwargs).successful()
                finally:
                    message.ack()
            finally:
                inbox.close()
        assert results(material_client, "quartz")[0]["id"] == material["id"]
        assert (
            material_client.get(f"{BASE}/{material['id']}/content").content
            == b"Quartz network search"
        )
    finally:
        if key is not None:
            objects.delete(key)
        objects.client.close()
        keys = list(redis.scan_iter(match=f"{queue}:*"))
        if keys:
            redis.delete(*keys)
        redis.close()
        app.close()


def test_legacy_extraction_is_requeued_by_materials_and_preserves_original(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    body = pdf_bytes("A located lecture")
    material = upload(material_client, body, "lecture.pdf", "application/pdf")
    process(concurrent_engine, material_client, material)
    with Session(concurrent_engine) as database, database.begin():
        text = database.get(MaterialSearchDocumentModel, UUID(material["id"]))
        assert text is not None and text.locations[0]["number"] == 1
        text.extraction_revision, text.locations = 0, []
    dispatch_materials(
        sessionmaker(concurrent_engine),
        storage(material_client),
        Mock(spec=Celery),
        reextract_legacy=True,
    )
    assert state(concurrent_engine, material) == "pending"
    process(concurrent_engine, material_client, material)
    assert state(concurrent_engine, material) == "ready"
    assert material_client.get(f"{BASE}/{material['id']}/content").content == body
    with Session(concurrent_engine) as database:
        text = database.get(MaterialSearchDocumentModel, UUID(material["id"]))
        assert text and text.extraction_revision == 1 and text.locations[0]["kind"] == "page"
