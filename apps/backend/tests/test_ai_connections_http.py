import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Event
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_ai_connections import KEY
from test_ai_connections import configuration as configuration
from test_ai_http import ai_client as ai_client
from test_ai_http import create, submit
from test_ai_openrouter import completion
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json

from app.integrations.llm.openrouter import openrouter_model
from app.modules.ai.infrastructure.connections import FileConnectionConfiguration
from app.modules.ai.infrastructure.orm import PersonalConnectionModel

BASE = "/api/v1/ai"


@pytest.fixture
def configured_client(ai_client: TestClient, configuration: FileConnectionConfiguration):
    application = cast(FastAPI, ai_client.app)
    application.state.settings = application.state.settings.model_copy(
        update={"ai_connections_file": configuration.path}
    )
    yield ai_client


def personal(client: TestClient):
    response = client.post(
        f"{BASE}/connections",
        headers=csrf_headers(client),
        json={"label": "Personal test account", "key": KEY},
    )
    assert response.status_code == 201, response.text
    return response.json()


def real_chat(client: TestClient, connection_id=None):
    response = client.post(
        f"{BASE}/conversations",
        headers=csrf_headers(client),
        json={
            "title": "Synthetic real-model chat",
            "offering_id": "flash",
            "connection_id": connection_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_connections_require_csrf_mask_secrets_and_never_validate_automatically(
    configured_client: TestClient,
    concurrent_engine: Engine,
    password_hash: str,
):
    client = configured_client
    with (
        patch.object(
            httpx.HTTPTransport, "handle_request", side_effect=AssertionError("No network")
        ),
        capture_json() as logs,
    ):
        assert (
            client.post(f"{BASE}/connections", json={"label": "T", "key": KEY}).status_code == 403
        )
        connection = personal(client)
        assert connection["key_mask"] == "********" and KEY not in str(connection)
        assert not {"key", "encrypted_key", "encryption_key_id", "user_id"}.intersection(connection)
        assert client.get(f"{BASE}/connections").json()["items"] == [connection]
        for invalid in ("too-short", "x" * 1025, KEY + "\x00", KEY + " "):
            response = client.post(
                f"{BASE}/connections",
                headers=csrf_headers(client),
                json={"label": "T", "key": invalid},
            )
            assert response.status_code == 422 and invalid not in response.text
        with Session(concurrent_engine) as database:
            stored = database.scalar(select(PersonalConnectionModel))
            assert stored is not None and stored.encrypted_key is not None
            assert KEY.encode() not in stored.encrypted_key
        seed_user(concurrent_engine, "other@example.com", password_hash)
        browser_login(client, "other@example.com")
        assert client.get(f"{BASE}/connections").json()["items"] == []
        assert (
            client.delete(
                f"{BASE}/connections/{connection['id']}", headers=csrf_headers(client)
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"{BASE}/connections/{connection['id']}/rotate", headers=csrf_headers(client)
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"{BASE}/conversations",
                headers=csrf_headers(client),
                json={"title": "T", "offering_id": "flash", "connection_id": connection["id"]},
            ).status_code
            == 404
        )
    assert KEY not in logs.getvalue()


@pytest.mark.parametrize("source", ["operator", "personal"])
def test_selected_model_accounting_replay_and_history_are_bound_to_new_chat(
    configured_client: TestClient,
    configuration: FileConnectionConfiguration,
    source: str,
):
    client = configured_client
    identifier = personal(client)["id"] if source == "personal" else None
    conversation = real_chat(client, identifier)
    assert conversation["model"] == "deepseek/deepseek-v4.1-flash"
    assert conversation["connection_id"] == identifier and conversation["offering_version"] == 1
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=completion(
                usage={"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}
            ),
        )

    with patch(
        "app.modules.ai.infrastructure.providers.openrouter_model",
        partial(openrouter_model, transport=httpx.MockTransport(respond)),
    ):
        response = submit(client, conversation, "Synthetic request")
        run = response.json()
        assert run["status"] == "completed", response.text
        assert run["provider"] == "openrouter" and run["model"] == conversation["model"]
        assert run["connection_id"] == identifier and run["tools"] == []
        assert run["attempts"][0]["input_tokens"] == 12
        assert run["attempts"][0]["output_tokens"] == 4
        assert len(requests) == 1
        assert submit(client, conversation, "Synthetic request", run["submission_id"]).json() == run
        assert len(requests) == 1
        data = json.loads(configuration.path.read_text())
        data["entries"][0]["model"] = "deepseek/different-model"
        configuration.path.write_text(json.dumps(data))
        assert submit(client, conversation, "Must not switch").status_code == 503
        assert len(requests) == 1
    assert (
        client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"][-1][
            "content"
        ]
        == "Synthetic answer"
    )
    fake = create(client)
    assert fake["offering_id"] is None and fake["provider"] == "fake"


def test_catalog_permissions_apply_to_existing_chats_without_an_admin_role(
    configured_client: TestClient,
    configuration: FileConnectionConfiguration,
):
    client = configured_client
    conversation = real_chat(client)
    data = json.loads(configuration.path.read_text())
    data["entries"][0].update(public=False, allowed_user_ids=[str(uuid4())])
    configuration.path.write_text(json.dumps(data))
    assert client.get(f"{BASE}/models").json() == []
    assert submit(client, conversation).status_code == 404
    assert (
        client.post(
            f"{BASE}/conversations",
            headers=csrf_headers(client),
            json={"title": "T", "offering_id": "flash"},
        ).status_code
        == 404
    )


def test_disconnect_cancels_inflight_prevents_new_dispatch_and_erases_secret(
    configured_client: TestClient,
    concurrent_engine: Engine,
):
    client = configured_client
    connection = personal(client)
    conversation = real_chat(client, connection["id"])
    entered, release = Event(), Event()
    requests = []

    def respond(request):
        requests.append(request)
        entered.set()
        assert release.wait(10)
        return httpx.Response(
            200,
            json=completion(
                usage={
                    "prompt_tokens": 8,
                    "completion_tokens": 2,
                    "total_tokens": 10,
                }
            ),
        )

    headers = csrf_headers(client)
    with (
        patch(
            "app.modules.ai.infrastructure.providers.openrouter_model",
            partial(openrouter_model, transport=httpx.MockTransport(respond)),
        ),
        ThreadPoolExecutor(1) as pool,
    ):
        pending = pool.submit(submit, client, conversation)
        try:
            assert entered.wait(10)
            response = client.delete(f"{BASE}/connections/{connection['id']}", headers=headers)
            assert response.status_code == 204
            assert submit(client, conversation).status_code == 503
        finally:
            release.set()
        run = pending.result(timeout=10).json()
        assert run["status"] == "cancelled"
        assert run["attempts"][0]["status"] == "interrupted"
        assert run["attempts"][0]["input_tokens"] == 8
        assert run["attempts"][0]["output_tokens"] == 2
    assert len(requests) == 1
    assert (
        len(client.get(f"{BASE}/conversations/{conversation['id']}/messages").json()["items"]) == 1
    )
    with Session(concurrent_engine) as database:
        row = database.get(PersonalConnectionModel, UUID(connection["id"]))
        assert row is not None and row.encrypted_key is None and row.encryption_key_id is None
