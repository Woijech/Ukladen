from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.modules.auth.presentation.dependencies import get_current_session, get_database
from app.modules.materials.application.excerpts import MaterialExcerptService
from app.modules.materials.presentation.routes import install_materials


def test_reader_http_bounds_owner_scope_and_unavailable_text() -> None:
    owner, identifier = uuid4(), uuid4()
    database = Mock()
    database.begin.side_effect = lambda: nullcontext()
    materials, users, text = Mock(), Mock(), Mock()
    materials.get.return_value = SimpleNamespace(
        id=identifier, title="Lecture", version=3, trashed_at=None, kind="file", status="ready"
    )
    users.is_active.return_value = True
    text.read.return_value = ("я🙂", 2002)
    service = MaterialExcerptService(materials, users, text)
    app = FastAPI()
    app.dependency_overrides[get_current_session] = lambda: SimpleNamespace(user_id=owner)
    app.dependency_overrides[get_database] = lambda: database
    install_materials(app)
    with (
        patch(
            "app.modules.materials.presentation.routes.MaterialExcerptService", return_value=service
        ),
        TestClient(app) as client,
    ):
        path = f"/api/v1/materials/{identifier}/text"
        response = client.get(path + "?offset=2000&limit=2")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "material_id": str(identifier),
            "title": "Lecture",
            "version": 3,
            "text": "я🙂",
            "offset": 2000,
            "total_characters": 2002,
        }
        materials.get.assert_called_with(owner, identifier)
        text.read.assert_called_once_with(owner, identifier, 2000, 2)
        for query in ("offset=-1", "offset=2097153", "limit=0", "limit=2001"):
            assert client.get(path + "?" + query).status_code == 422
        materials.get.return_value.status = "processing"
        assert client.get(path).json() is None
        materials.get.return_value.trashed_at = "trashed"
        assert client.get(path).status_code == 404
        materials.get.return_value = None
        assert client.get(path).status_code == 404

        def unauthenticated():
            raise HTTPException(status_code=401)

        app.dependency_overrides[get_current_session] = unauthenticated
        assert client.get(path).status_code == 401
