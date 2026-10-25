import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import create, submit
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import enrolled as enrolled
from test_calendar_http import store as store
from test_schedule_expansion import schedule_fixture

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.actions import ActionBatch, ActionService
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.infrastructure.action_models import ActionProposalModel, ActionReceiptModel
from app.modules.ai.infrastructure.action_tools import action_tool
from app.modules.ai.infrastructure.actions import SqlAlchemyActionTransactions
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.fake_tools import fake_double
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import ProviderAttemptModel
from app.modules.ai.infrastructure.retention import purge_expired
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.ai.presentation.routes import get_ai
from app.modules.calendar.infrastructure.orm import PersonalCalendarEventModel
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.reminders.application.service import ReminderService
from app.modules.reminders.infrastructure.orm import ReminderModel
from app.modules.schedule.application.expansion import expand_schedule
from app.modules.schedule.infrastructure.orm import OfficialScheduleEventModel
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.search.domain.evidence import SourceReference

BASE = "/api/v1/ai"


def page_action(title="Synthetic page") -> dict:
    return {
        "operation": "page_create",
        "title": title,
        "document": {
            "schema_version": 1,
            "blocks": [{"id": str(uuid4()), "type": "text", "text": "Private body"}],
        },
    }


def event_action() -> dict:
    start = datetime.now(UTC) + timedelta(days=2)
    return {
        "operation": "event_create",
        "title": "Training",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=1)).isoformat(),
        "blocks_time": True,
    }


def script(client: TestClient, actions: list[dict]) -> AiService:
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"ai_actions_enabled": True})
    sessions = app.state.session_factory
    sources = SqlAlchemySourceReader(sessions, app.state.academic_provider, 3600)
    service = AiService(
        SqlAlchemyAiTransactions(sessions),
        PostgresAgentRunners(
            sessions,
            model=lambda: FakeChatModel(
                responses=(
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "propose_actions",
                                "args": {"actions": actions},
                                "id": str(uuid4()),
                                "type": "tool_call",
                            }
                        ],
                    ),
                )
            ),
            actions_enabled=True,
        ),
        actions=ActionService(SqlAlchemyActionTransactions(sources)),
    )
    app.dependency_overrides[get_ai] = lambda: service
    return service


def propose(client: TestClient, actions: list[dict], conversation: dict | None = None):
    script(client, actions)
    conversation = conversation or create(client)
    result = submit(client, conversation)
    assert result.status_code == 200 and result.json()["status"] == "completed", result.text
    proposals = client.get(f"{BASE}/conversations/{conversation['id']}/proposals")
    assert proposals.status_code == 200 and proposals.json(), proposals.text
    return conversation, proposals.json()[0]


def decide(client: TestClient, proposal: dict, decision="approve"):
    return client.post(
        f"{BASE}/proposals/{proposal['id']}/decision",
        headers=csrf_headers(client),
        json={"digest": proposal["digest"], "decision": decision},
    )


def count(engine: Engine, model) -> int:
    with Session(engine) as database:
        return database.scalar(select(func.count()).select_from(model)) or 0


def test_batch_preview_atomic_replay_and_model_free_confirmation(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation, proposal = propose(
        ai_client,
        [
            page_action(),
            event_action(),
            {
                "operation": "reminder_create",
                "event_action": 1,
                "minutes_before": 30,
            },
        ],
    )
    assert datetime.fromisoformat(proposal["expires_at"]) - datetime.fromisoformat(
        proposal["created_at"]
    ) == timedelta(hours=24)
    models = (PageModel, PersonalCalendarEventModel, ReminderModel)
    assert all(count(concurrent_engine, model) == 0 for model in models)
    attempts = count(concurrent_engine, ProviderAttemptModel)
    with patch.object(
        FakeChatModel, "_generate", side_effect=AssertionError("No model on confirmation")
    ):
        first = decide(ai_client, proposal)
        assert first.status_code == 200 and first.json()["status"] == "applied", first.text
        assert decide(ai_client, proposal).json() == first.json()
        assert decide(ai_client, proposal, "reject").json() == first.json()
    assert all(count(concurrent_engine, model) == 1 for model in models)
    assert count(concurrent_engine, ProviderAttemptModel) == attempts
    with Session(concurrent_engine) as database:
        event, reminder = (
            database.scalar(select(PersonalCalendarEventModel)),
            database.scalar(select(ReminderModel)),
        )
        assert event and reminder and reminder.personal_event_id == event.id
        assert reminder.due_at == event.starts_at - timedelta(minutes=30)
    script(ai_client, [page_action("Second")])
    assert submit(ai_client, conversation, "Create another page").json()["status"] == "completed"
    assert count(concurrent_engine, PageModel) == 1


def test_reject_expiry_supersession_csrf_and_owner(
    ai_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    conversation, proposal = propose(ai_client, [page_action()])
    url = f"{BASE}/proposals/{proposal['id']}/decision"
    payload = {"digest": proposal["digest"], "decision": "approve"}
    assert ai_client.post(url, json=payload).status_code == 403
    assert (
        ai_client.post(
            url,
            headers=csrf_headers(ai_client) | {"Origin": "https://attacker.example"},
            json=payload,
        ).status_code
        == 403
    )
    assert (
        ai_client.post(
            url, headers=csrf_headers(ai_client), json=payload | {"digest": "0" * 64}
        ).status_code
        == 409
    )
    assert (
        ai_client.post(
            url, headers=csrf_headers(ai_client), json=payload | {"approved": True}
        ).status_code
        == 422
    )
    assert decide(ai_client, proposal, "reject").json()["status"] == "rejected"
    assert decide(ai_client, proposal).json()["status"] == "rejected"
    _, expiring = propose(ai_client, [page_action()], conversation)
    service = cast(FastAPI, ai_client.app).dependency_overrides[get_ai]()
    assert service.actions is not None
    service.actions.now = lambda: datetime.fromisoformat(expiring["expires_at"])
    assert decide(ai_client, expiring).json()["status"] == "expired"
    _, old = propose(ai_client, [page_action()], conversation)
    propose(ai_client, [page_action()], conversation)
    assert decide(ai_client, old).json()["status"] == "superseded"
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(ai_client, "other@example.com")
    assert ai_client.get(f"{BASE}/conversations/{conversation['id']}/proposals").status_code == 404
    assert decide(ai_client, old).status_code == 404
    assert count(concurrent_engine, PageModel) == 0


def test_rollback_and_concurrent_confirmation_then_content_cleanup(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    conversation, proposal = propose(
        ai_client,
        [
            page_action(),
            event_action(),
            {
                "operation": "reminder_create",
                "event_action": 1,
                "minutes_before": 15,
            },
        ],
    )
    with patch.object(ReminderService, "create", side_effect=SQLAlchemyError("private-error")):
        failed = decide(ai_client, proposal)
    assert failed.status_code == 503 and "private-error" not in failed.text
    assert all(
        count(concurrent_engine, model) == 0
        for model in (PageModel, PersonalCalendarEventModel, ReminderModel, ActionReceiptModel)
    )
    headers = csrf_headers(ai_client)
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(
                ai_client.post,
                f"{BASE}/proposals/{proposal['id']}/decision",
                headers=headers,
                json={"digest": proposal["digest"], "decision": "approve"},
            )
            for _ in range(2)
        ]
        results = [future.result(timeout=15) for future in futures]
    assert all(item.status_code == 200 for item in results)
    assert results[0].json() == results[1].json() and count(concurrent_engine, PageModel) == 1
    assert (
        ai_client.delete(f"{BASE}/conversations/{conversation['id']}", headers=headers).status_code
        == 204
    )
    assert count(concurrent_engine, ActionProposalModel) == 0
    assert count(concurrent_engine, ActionReceiptModel) == count(concurrent_engine, PageModel) == 1
    assert decide(ai_client, proposal).status_code == 404
    purge_expired(
        cast(FastAPI, ai_client.app).state.session_factory,
        now=datetime.now(UTC) + timedelta(days=31),
    )
    assert count(concurrent_engine, ActionReceiptModel) == 1
    with Session(concurrent_engine) as database:
        receipt = database.scalar(select(ActionReceiptModel))
        assert receipt and "Private body" not in json.dumps(receipt.outcomes)


def test_edits_versions_disable_and_deleted_chats(
    ai_client: TestClient, concurrent_engine: Engine
) -> None:
    headers = csrf_headers(ai_client)
    block_id = str(uuid4())
    page = ai_client.post(
        "/api/v1/notes/pages",
        headers=headers,
        json={
            "title": "Original",
            "document": {
                "schema_version": 1,
                "blocks": [{"id": block_id, "type": "text", "text": "Before"}],
            },
        },
    ).json()
    event = ai_client.post(
        "/api/v1/calendar/personal-events",
        headers=headers,
        json={key: value for key, value in event_action().items() if key != "operation"}
        | {"description": "Keep my description", "location": "Gym"},
    ).json()
    edit = {
        "operation": "event_update",
        "event_id": event["id"],
        "expected_version": 1,
        "changes": {"title": "Changed"},
    }
    conversation, proposal = propose(
        ai_client,
        [
            {
                "operation": "page_update",
                "page_id": page["id"],
                "expected_version": 1,
                "title": "Improved",
                "document": {
                    "schema_version": 1,
                    "blocks": [{"id": block_id, "type": "text", "text": "After"}],
                },
            },
            edit,
        ],
    )
    app = cast(FastAPI, ai_client.app)
    app.state.settings = app.state.settings.model_copy(update={"ai_actions_enabled": False})
    assert decide(ai_client, proposal).status_code == 503
    app.state.settings = app.state.settings.model_copy(update={"ai_actions_enabled": True})
    assert decide(ai_client, proposal).json()["status"] == "applied"
    saved = ai_client.get(f"/api/v1/notes/pages/{page['id']}").json()
    assert saved["title"] == "Improved" and saved["document"]["blocks"][0]["id"] == block_id
    saved_event = ai_client.get(f"/api/v1/calendar/personal-events/{event['id']}").json()
    assert saved_event["title"] == "Changed"
    assert saved_event["description"] == "Keep my description" and saved_event["location"] == "Gym"
    _, stale = propose(
        ai_client,
        [
            event_action(),
            {
                "operation": "page_update",
                "page_id": page["id"],
                "expected_version": saved["version"],
                "title": "Stale",
            },
        ],
        conversation,
    )
    ai_client.patch(
        f"/api/v1/notes/pages/{page['id']}",
        headers=headers,
        json={"expected_version": saved["version"], "title": "Manual"},
    )
    assert decide(ai_client, stale).status_code == 409
    assert count(concurrent_engine, PersonalCalendarEventModel) == 1
    _, pending = propose(ai_client, [page_action()], conversation)
    assert (
        ai_client.delete(f"{BASE}/conversations/{conversation['id']}", headers=headers).status_code
        == 204
    )
    assert decide(ai_client, pending).status_code == 404
    assert count(concurrent_engine, PageModel) == 1


@pytest.mark.parametrize(
    "actions",
    [
        [{"operation": "delete", "event_id": str(uuid4())}],
        [{"operation": "reminder_create", "event_action": 0, "minutes_before": 15}],
        [event_action() | {"starts_at": "2026-10-26T18:00:00"}],
        [event_action() | {"blocks_time": "true"}],
        [page_action() | {"owner_id": str(uuid4())}],
    ],
)
def test_action_boundary_rejects_unsupported_arguments(actions: list[dict]) -> None:
    with pytest.raises(ValidationError):
        ActionBatch.model_validate({"actions": actions})


@pytest.mark.parametrize("mixed_reads", [False, True])
def test_hitl_settles_without_replaying_tool(mixed_reads: bool) -> None:
    identifier = uuid4()
    model = FakeChatModel(
        responses=(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_actions",
                        "args": {"actions": [page_action()]},
                        "id": "proposal",
                        "type": "tool_call",
                    }
                ]
                + (
                    [
                        {
                            "name": "fake_double",
                            "args": {"value": 7},
                            "id": "deferred-read",
                            "type": "tool_call",
                        }
                    ]
                    if mixed_reads
                    else []
                ),
            ),
            AIMessage(content="Next turn"),
        )
    )
    checkpoints = InMemorySaver()
    runner = OfflineAgentRunner(
        model,
        [action_tool(), fake_double],
        checkpoints,
        review_tools=frozenset({"propose_actions"}),
        action_status=lambda _: "applied",
    )
    assert (
        runner.run(AgentInput(conversation_id=identifier, message="Create")).status == "interrupted"
    )
    runner = OfflineAgentRunner(
        FakeChatModel(responses=(AIMessage(content="Next turn"),)),
        [action_tool(), fake_double],
        checkpoints,
        review_tools=frozenset({"propose_actions"}),
        action_status=lambda _: "applied",
    )
    second = runner.run(AgentInput(conversation_id=identifier, message="Continue"))
    assert second.status == "completed" and second.answer == "Next turn"


def test_official_source_changes_block_confirmation_even_without_revision(
    enrolled: TestClient,
    store: SqlAlchemyScheduleStore,
    concurrent_engine: Engine,
) -> None:
    app = cast(FastAPI, enrolled.app)
    app.state.settings = app.state.settings.model_copy(update={"ai_enabled": True})
    now = datetime.now(UTC)
    snapshot = schedule_fixture()
    event = replace(
        expand_schedule(snapshot)[0],
        subgroup=0,
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=1),
    )
    token = store.claim(24066, "353501", now)
    assert token and store.apply(24066, token, snapshot, [event], now)
    script(enrolled, [page_action()])
    timezone = ZoneInfo(enrolled.get("/api/v1/users/me").json()["timezone"])
    query = {
        "date_from": event.starts_at.astimezone(timezone).date().isoformat(),
        "date_to": event.ends_at.astimezone(timezone).date().isoformat(),
    }
    response = enrolled.post(BASE + "/sources/read", headers=csrf_headers(enrolled), json=query)
    assert response.status_code == 200, response.text
    reference = SourceReference.model_validate(response.json()["sources"][0])
    assert reference.source == "official" and reference.fingerprint is not None
    original = ActionService.propose

    def capture(self, run, review, sources=()):
        return original(self, run, review, (reference,))

    with patch.object(ActionService, "propose", capture):
        _, proposal = propose(enrolled, [page_action()])
    with Session(concurrent_engine) as database, database.begin():
        database.execute(
            update(OfficialScheduleEventModel)
            .where(OfficialScheduleEventModel.id == event.id)
            .values(
                starts_at=event.starts_at + timedelta(minutes=30),
                ends_at=event.ends_at + timedelta(minutes=30),
            )
        )
    assert decide(enrolled, proposal).status_code == 409
    current = enrolled.post(
        BASE + "/sources/read", headers=csrf_headers(enrolled), json=query
    ).json()["sources"][0]
    assert (
        current["version"] == reference.version and current["fingerprint"] != reference.fingerprint
    )
    assert count(concurrent_engine, PageModel) == 0
