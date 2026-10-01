from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.health import HealthChecks
from app.db.session import create_database_engine
from app.main import create_app


def test_health_endpoints_and_dependency_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:8333")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    monkeypatch.setenv("S3_BUCKET", "test")
    with (
        patch.object(HealthChecks, "check_postgres"),
        patch.object(HealthChecks, "check_redis") as redis_check,
        patch.object(HealthChecks, "check_storage"),
        TestClient(create_app()) as client,
    ):
        assert client.get("/api/health/live").json()["status"] == "ok"
        response = client.get("/api/health/ready")
        assert response.status_code == 200
        assert response.json()["checks"] == {"postgres": True, "redis": True, "storage": True}
        redis_check.side_effect = ConnectionError("secret connection details")
        response = client.get("/api/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["redis"] is False
        assert "secret" not in response.text
        assert client.get("/api/health/live").status_code == 200
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"]["title"] == "Ukladen"


def test_settings_reject_invalid_connection_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "not-a-database-url")
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_storage_readiness_probe() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql+psycopg://test:test@localhost:5432/test",
            "redis_url": "redis://localhost:6379/0",
            "s3_endpoint": "http://localhost:8333",
            "s3_access_key": "test",
            "s3_secret_key": "test",
            "s3_bucket": "test",
        }
    )
    engine = create_database_engine(settings)
    health = HealthChecks(engine, settings)
    health.http.close()

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:8333/readyz"
        return httpx.Response(200)

    try:
        health.http = httpx.Client(
            base_url=str(settings.s3_endpoint), transport=httpx.MockTransport(respond)
        )
        health.check_storage()
        health.http.close()
        health.http = httpx.Client(
            base_url=str(settings.s3_endpoint),
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        )
        with pytest.raises(httpx.HTTPStatusError):
            health.check_storage()
    finally:
        health.close()
        engine.dispose()
