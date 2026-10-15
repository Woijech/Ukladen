import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import BinaryIO, cast
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json
from test_notes_http import create_page

from app.core.config import Settings
from app.integrations.storage.materials import S3MaterialStorage
from app.modules.materials.domain.materials import MAX_FILE_BYTES
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.materials.infrastructure.repository import SqlAlchemyMaterialRepository

BASE = "/api/v1/materials"


class MemoryMaterialStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, body: BinaryIO, size: int, media_type: str) -> None:
        self.objects[key] = body.read()

    def get(self, key: str, size: int) -> BinaryIO | None:
        content = self.objects.get(key)
        return BytesIO(content) if content is not None else None

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def close(self) -> None:
        pass


@pytest.fixture
def material_client(calendar_client: TestClient) -> Iterator[TestClient]:
    application = cast(FastAPI, calendar_client.app)
    application.state.material_storage.close()
    application.state.material_storage = MemoryMaterialStorage()
    yield calendar_client


def reserve(client: TestClient, filename: str = "lecture.txt", size: int = 5) -> dict:
    response = client.post(
        BASE + "/uploads",
        headers=csrf_headers(client),
        json={"filename": filename, "size_bytes": size},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(
    client: TestClient,
    content: bytes = b"study",
    filename: str = "lecture.txt",
    media_type: str = "text/plain",
) -> dict:
    material = reserve(client, filename, len(content))
    response = client.put(
        f"{BASE}/{material['id']}/content",
        content=content,
        headers=csrf_headers(client) | {"Content-Type": media_type},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_download_versions_trash_and_logs(material_client: TestClient) -> None:
    with capture_json() as output:
        material = upload(material_client)
        path, headers = f"{BASE}/{material['id']}", csrf_headers(material_client)
        assert material["status"] == "pending" and material["version"] == 2
        assert (
            "user_id" not in material
            and "storage_key" not in material
            and "lease_token" not in material
        )
        assert material_client.get(BASE).json()["items"] == [material]
        usage = material_client.get(BASE + "/storage").json()
        assert usage["used_bytes"] == 5 and usage["limit_bytes"] == 1024**3
        assert usage["max_file_bytes"] == MAX_FILE_BYTES
        response = material_client.get(path + "/content")
        assert response.status_code == 200 and response.content == b"study"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert (
            material_client.put(
                path + "/content",
                content=b"other",
                headers=headers | {"Content-Type": "text/plain"},
            ).status_code
            == 409
        )
        changed = material_client.patch(
            path, headers=headers, json={"expected_version": 2, "title": "Private title"}
        )
        assert changed.status_code == 200 and changed.json()["version"] == 3
        assert (
            material_client.patch(
                path, headers=headers, json={"expected_version": 2, "title": "Stale"}
            ).status_code
            == 409
        )
        trashed = material_client.post(
            path + "/trash", headers=headers, json={"expected_version": 3}
        )
        assert trashed.status_code == 200 and trashed.json()["trashed_at"]
        assert material_client.get(BASE).json()["items"] == []
        assert material_client.get(BASE + "?trashed=true").json()["items"] == [trashed.json()]
        assert material_client.get(path + "/content").status_code == 409
        assert material_client.get(BASE + "/storage").json()["used_bytes"] == 5
        restored = material_client.post(
            path + "/restore", headers=headers, json={"expected_version": 4}
        )
        assert restored.status_code == 200 and restored.json()["trashed_at"] is None
        assert material_client.get(path + "/content").content == b"study"
    assert "Private title" not in output.getvalue() and "lecture.txt" not in output.getvalue()
    assert material_client.get(BASE).headers["cache-control"] == "no-store"


def test_links_are_bookmarks_and_page_links_are_optional(material_client: TestClient) -> None:
    response = material_client.post(
        BASE + "/links",
        headers=csrf_headers(material_client),
        json={"title": "Course", "url": "https://example.com/private-lecture"},
    )
    assert response.status_code == 201 and response.json()["status"] == "ready"
    material, page = response.json(), create_page(material_client)
    path = f"/api/v1/relations/pages/{page['id']}/materials/{material['id']}"
    for _ in range(2):
        assert material_client.put(path, headers=csrf_headers(material_client)).status_code == 200
    assert material_client.get(f"/api/v1/relations/pages/{page['id']}/materials").json()[
        "items"
    ] == [material]
    assert (
        material_client.get(f"/api/v1/relations/materials/{material['id']}/pages").json()["items"][
            0
        ]["id"]
        == page["id"]
    )
    assert material_client.delete(path, headers=csrf_headers(material_client)).status_code == 204
    assert material_client.get(f"{BASE}/{material['id']}").status_code == 200
    assert material_client.get(f"/api/v1/notes/pages/{page['id']}").status_code == 200
    storage = cast(FastAPI, material_client.app).state.material_storage
    assert storage.objects == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"filename": "x.exe", "size_bytes": 1},
        {"filename": "../x.txt", "size_bytes": 1},
        {"filename": "x.txt", "size_bytes": True},
        {"filename": "x.txt", "size_bytes": 0},
        {"filename": "x.txt", "size_bytes": MAX_FILE_BYTES + 1},
        {"filename": "x.txt", "size_bytes": 1, "user_id": "foreign"},
    ],
)
def test_upload_intent_validation(material_client: TestClient, payload: dict) -> None:
    assert (
        material_client.post(
            BASE + "/uploads", headers=csrf_headers(material_client), json=payload
        ).status_code
        == 422
    )
    assert material_client.get(BASE + "/storage").json()["used_bytes"] == 0


def test_chunked_size_mime_and_file_signature_validation(material_client: TestClient) -> None:
    material = reserve(material_client)
    path = f"{BASE}/{material['id']}/content"
    headers = csrf_headers(material_client)
    for content, media_type in ((b"x", "text/plain"), (b"study", "application/pdf")):
        assert (
            material_client.put(
                path, content=content, headers=headers | {"Content-Type": media_type}
            ).status_code
            == 422
        )
    assert (
        material_client.put(
            path,
            content=(b"x" * (1024 * 1024) for _ in range(26)),
            headers=headers | {"Content-Type": "text/plain"},
        ).status_code
        == 413
    )
    pdf = reserve(material_client, "wrong.pdf", 5)
    assert (
        material_client.put(
            f"{BASE}/{pdf['id']}/content",
            content=b"wrong",
            headers=headers | {"Content-Type": "application/pdf"},
        ).status_code
        == 422
    )


def test_access_controls_and_foreign_page_links(
    material_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    material, page = upload(material_client), create_page(material_client)
    path = f"{BASE}/{material['id']}"
    assert (
        material_client.post(
            BASE + "/uploads", json={"filename": "x.txt", "size_bytes": 1}
        ).status_code
        == 403
    )
    assert material_client.post(path + "/trash", json={"expected_version": 2}).status_code == 403
    assert material_client.put(path + "/content", content=b"study").status_code == 403
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(material_client, "other@example.com")
    headers = csrf_headers(material_client)
    for suffix in ("", "/content"):
        assert material_client.get(path + suffix).status_code == 404
    assert material_client.get(BASE).json()["items"] == []
    assert material_client.get(BASE + "/storage").json()["used_bytes"] == 0
    assert (
        material_client.post(
            path + "/trash", headers=headers, json={"expected_version": 2}
        ).status_code
        == 404
    )
    own = upload(material_client)
    assert (
        material_client.put(
            f"/api/v1/relations/pages/{page['id']}/materials/{own['id']}", headers=headers
        ).status_code
        == 404
    )
    assert (
        material_client.put(
            f"/api/v1/relations/pages/{page['id']}/materials/{material['id']}", headers=headers
        ).status_code
        == 404
    )
    material_client.cookies.clear()
    assert material_client.get(BASE).status_code == 401
    assert material_client.get(path + "/content").status_code == 401


def test_failed_finalize_keeps_durable_upload_intent(material_client: TestClient) -> None:
    material = reserve(material_client)
    path = f"{BASE}/{material['id']}"
    with (
        patch.object(
            SqlAlchemyMaterialRepository, "save", side_effect=SQLAlchemyError("private-sql")
        ),
        capture_json() as output,
    ):
        response = material_client.put(
            path + "/content",
            content=b"study",
            headers=csrf_headers(material_client) | {"Content-Type": "text/plain"},
        )
    assert response.status_code == 503 and "private-sql" not in output.getvalue()
    assert material_client.get(path).json()["status"] == "uploading"
    storage = cast(FastAPI, material_client.app).state.material_storage
    assert len(storage.objects) == 1
    assert (
        material_client.put(
            path + "/content",
            content=b"study",
            headers=csrf_headers(material_client) | {"Content-Type": "text/plain"},
        ).status_code
        == 200
    )


def test_expired_upload_and_restore_are_rejected(
    material_client: TestClient, concurrent_engine: Engine
) -> None:
    material = reserve(material_client)
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(MaterialModel, UUID(material["id"]))
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(hours=2)
    path, headers = f"{BASE}/{material['id']}", csrf_headers(material_client)
    assert (
        material_client.put(
            path + "/content", content=b"study", headers=headers | {"Content-Type": "text/plain"}
        ).status_code
        == 409
    )
    assert (
        material_client.post(
            path + "/trash", headers=headers, json={"expected_version": 1}
        ).status_code
        == 200
    )
    with Session(concurrent_engine) as database, database.begin():
        row = database.get(MaterialModel, UUID(material["id"]))
        assert row is not None
        row.trashed_at = datetime.now(UTC) - timedelta(days=31)
    assert (
        material_client.post(
            path + "/restore", headers=headers, json={"expected_version": 2}
        ).status_code
        == 409
    )


def test_native_seaweedfs_material_upload_download(
    material_client: TestClient, settings: Settings
) -> None:
    endpoint = os.environ.get("AVATAR_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("Set disposable S3 test configuration for native material storage.")
    storage = S3MaterialStorage(
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
    application = cast(FastAPI, material_client.app)
    application.state.material_storage = storage
    keys = []
    try:
        material = upload(
            material_client, "Учебный материал".encode(), "Лекция.md", "text/markdown"
        )
        with application.state.session_factory() as database:
            row = database.get(MaterialModel, UUID(material["id"]))
            assert row is not None
            keys.append(f"materials/{row.user_id}/{row.id}")
        response = material_client.get(f"{BASE}/{material['id']}/content")
        assert response.status_code == 200 and response.content == "Учебный материал".encode()
    finally:
        for key in keys:
            storage.delete(key)
        storage.close()
