import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace

import pytest
from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import JsonFormatter, log_failure, request_id, task_id
from app.core.request_logging import RequestLoggingMiddleware
from app.main import create_app
from app.workers.logging import finish_task, install_task_logging, start_task


@contextmanager
def capture_json():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("app")
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def entries(stream: StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_safe_exception_locations_and_allowlisted_fields() -> None:
    secret = "private-password-token-email-sql-parameter"
    with capture_json() as output:
        try:
            raise RuntimeError(secret)
        except RuntimeError as error:
            log_failure(logging.getLogger("app.test"), "operation.failed", error, operation="read")
        logging.getLogger("app.test").info("operation.ready", extra={"password": secret})
    failure, success = entries(output)
    assert failure["error_type"] == "RuntimeError"
    assert (
        failure["traceback"][-1]["function"]
        == "test_safe_exception_locations_and_allowlisted_fields"
    )
    assert failure["operation"] == "read"
    assert "password" not in success
    assert secret not in output.getvalue()
    record = logging.LogRecord("uvicorn.error", logging.ERROR, "test", 1, secret, (), None)
    assert secret not in JsonFormatter().format(record)


def test_http_context_parallel_requests_and_unknown_path_redaction() -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/items/{identifier}")
    async def item(identifier: str):
        before = request_id.get()
        await asyncio.sleep(0.02)
        assert before == request_id.get()
        logging.getLogger("app.test").info("item.read")
        return {"request_id": before}

    with capture_json() as output, TestClient(app) as client, ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(
                lambda value: client.get(
                    f"/items/{value}?token=private-query",
                    headers={
                        "X-Request-ID": "untrusted-client-id",
                        "Authorization": "private-header",
                    },
                ),
                ["private-item-a", "private-item-b"],
            )
        )
        assert len({response.headers["x-request-id"] for response in responses}) == 2
        for response in responses:
            assert response.json()["request_id"] == response.headers["x-request-id"]
        assert client.get("/private-unmatched-url").status_code == 404
    records = entries(output)
    completed = [record for record in records if record["event"] == "http.request_completed"]
    assert {record["route"] for record in completed} == {"/items/{identifier}", "[unmatched]"}
    assert all("duration_ms" in record for record in completed)
    assert "private" not in output.getvalue()
    assert request_id.get() is None


@pytest.mark.parametrize("handled", [False, True])
def test_http_errors_have_safe_logs_and_request_id(handled: bool) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    app = create_app(
        Settings.model_validate(
            {
                "database_url": "postgresql+psycopg://test:test@localhost:5432/test",
                "redis_url": "redis://localhost:6379/0",
                "s3_endpoint": "http://localhost:8333",
                "s3_access_key": "test",
                "s3_secret_key": "test",
                "s3_bucket": "test",
            }
        )
    )

    @app.get("/failure")
    def fail():
        raise SQLAlchemyError("private-sql-values") if handled else RuntimeError("private-error")

    with capture_json() as output, TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure?token=private-query")
    assert response.status_code == (503 if handled else 500)
    assert len(response.headers["x-request-id"]) == 32
    assert "private" not in response.text and "private" not in output.getvalue()
    if not handled:
        failure = next(
            record for record in entries(output) if record["event"] == "http.unhandled_error"
        )
        assert failure["request_id"] == response.headers["x-request-id"]


def test_task_publish_propagates_request_context_and_execution_resets_it() -> None:
    from celery import signals

    install_task_logging()
    app = Celery("logging-test", broker="memory://", set_as_current=False)
    headers_seen = []

    def published(headers=None, **kwargs):
        headers_seen.append(dict(headers or {}))

    signals.after_task_publish.connect(published, weak=False)
    context = request_id.set("a" * 32)
    try:
        app.send_task("foundation.ping", ignore_result=True)
        task = SimpleNamespace(
            name="schedule.sync_group",
            request=SimpleNamespace(
                headers={"ukladen_request_id": "a" * 32}, update=lambda **kwargs: None
            ),
        )
        with capture_json() as output:
            start_task(task, "11111111-1111-1111-1111-111111111111")
            assert request_id.get() == "a" * 32
            assert task_id.get() == "11111111-1111-1111-1111-111111111111"
            finish_task(task, "SUCCESS")
            task.request.headers = {"ukladen_request_id": "private-invalid-header"}
            start_task(task, "private-invalid-task-id")
            assert request_id.get() is None
            finish_task(task, "SUCCESS")
        assert headers_seen[0]["ukladen_request_id"] == "a" * 32
        assert request_id.get() == "a" * 32 and task_id.get() is None
        first, finished, second, _ = entries(output)
        assert first["task_name"] == "schedule.sync_group"
        assert first["request_id"] == finished["request_id"] == "a" * 32
        assert "request_id" not in second and "private" not in output.getvalue()
    finally:
        request_id.reset(context)
        signals.after_task_publish.disconnect(published)
        app.close()
