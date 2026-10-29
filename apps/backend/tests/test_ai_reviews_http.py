from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import browser_login, csrf_headers, seed_user


def test_settings_are_disabled_private_versioned_and_csrf_protected(
    ai_client: TestClient, concurrent_engine: Engine, password_hash: str
):
    path = "/api/v1/ai/reviews/settings"
    original = ai_client.get(path)
    assert original.status_code == 200, original.text
    assert original.headers["cache-control"] == "no-store"
    assert original.json()["version"] == 0
    assert original.json()["configuration"]["enabled"] is False
    payload = {"configuration": {"daily_time": "10:15"}, "expected_version": 0}
    assert ai_client.put(path, json=payload).status_code == 403
    saved = ai_client.put(path, headers=csrf_headers(ai_client), json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert saved.json()["configuration"]["daily_time"] == "10:15"
    assert ai_client.put(path, headers=csrf_headers(ai_client), json=payload).status_code == 409
    payload["expected_version"] = 1
    payload["configuration"] = {"enabled": True}
    assert ai_client.put(path, headers=csrf_headers(ai_client), json=payload).status_code == 422
    seed_user(concurrent_engine, "reviews-other@example.com", password_hash)
    browser_login(ai_client, "reviews-other@example.com")
    assert ai_client.get(path).json()["version"] == 0
    ai_client.cookies.clear()
    assert ai_client.get(path).status_code == 401


def test_settings_storage_failure_is_unavailable(ai_client: TestClient):
    from unittest.mock import patch

    from sqlalchemy.exc import SQLAlchemyError

    from app.modules.ai.infrastructure.review_settings import SqlAlchemyReviewSettings

    with patch.object(SqlAlchemyReviewSettings, "get", side_effect=SQLAlchemyError("private")):
        response = ai_client.get("/api/v1/ai/reviews/settings")
    assert response.status_code == 503
    assert "private" not in response.text
