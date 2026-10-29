from contextlib import contextmanager
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_ai_actions import count, decide, propose, script
from test_ai_http import ai_client as ai_client
from test_ai_http import browser_settings as browser_settings
from test_ai_http import calendar_client as calendar_client
from test_ai_http import concurrent_engine as concurrent_engine
from test_ai_http import create, submit
from test_ai_http import live_client as live_client
from test_ai_http import password_hash as password_hash
from test_ai_http import settings as settings
from test_auth_http import csrf_headers
from test_task_plans import proposal as task_plan
from test_tasks_http import BASE as TASKS
from test_tasks_http import create_task

from app.integrations.llm.fake import FakeChatModel
from app.modules.ai.application.actions import ActionBatch, ActionService
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.application.source_queries import (
    SourceScope,
    TaskRead,
    restrict_source_query,
)
from app.modules.ai.infrastructure.action_tools import action_tool
from app.modules.ai.infrastructure.actions import SqlAlchemyActionTransactions
from app.modules.ai.infrastructure.agent import OfflineAgentRunner
from app.modules.ai.infrastructure.grounding import SourceTools
from app.modules.ai.infrastructure.lifecycle import SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.ai.presentation.routes import get_ai
from app.modules.relations.infrastructure.orm import TaskPageLinkModel
from app.modules.tasks.infrastructure.orm import TaskDependencyModel, TaskModel, TaskOriginModel
from app.modules.tasks.infrastructure.planning import WorkSessionModel


def draft(title="Read chapter", **extra):
    return {
        "operation": "task_create",
        "task": {"title": title, "estimated_minutes": 45, "remaining_minutes": 45},
        "estimate_kind": "estimate",
    } | extra


def test_confirmed_task_batch_subtasks_dependencies_revision_and_replay(
    ai_client: TestClient, concurrent_engine: Engine
):
    client = ai_client
    existing = create_task(client, title="Read chapter")
    conversation, preview = propose(
        client, [draft(), draft("Review", parent_action=0, predecessor_actions=[0])]
    )
    assert preview["effects"][0]["after"]["possible_duplicates"][0]["id"] == existing["id"]
    assert count(concurrent_engine, TaskModel) == 1
    batch = preview["batch"]
    batch["actions"][0]["task"]["title"] = "Read corrected chapter"
    revised = client.post(
        "/api/v1/ai/proposals/" + preview["id"] + "/revise",
        headers=csrf_headers(client),
        json=batch,
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["id"] != preview["id"] and revised.json()["digest"] != preview["digest"]
    assert decide(client, preview).json()["status"] == "superseded"
    with patch.object(
        FakeChatModel, "_generate", side_effect=AssertionError("No model on confirmation")
    ):
        applied = decide(client, revised.json())
        assert applied.status_code == 200 and applied.json()["status"] == "applied", applied.text
        assert decide(client, revised.json()).json() == applied.json()
    assert count(concurrent_engine, TaskModel) == 3
    assert count(concurrent_engine, TaskDependencyModel) == 1
    root, child = applied.json()["outcomes"]
    assert client.get(TASKS + "/" + child["target_id"]).json()["parent_id"] == root["target_id"]
    assert (
        client.get(TASKS + "/" + root["target_id"] + "/origin").json()["estimate_kind"]
        == "estimate"
    )


def test_task_update_versions_remaining_and_atomic_rollback(
    ai_client: TestClient, concurrent_engine: Engine
):
    client = ai_client
    task = create_task(client, remaining_minutes=90)
    action = {
        "operation": "task_update",
        "task_id": task["id"],
        "expected_version": 1,
        "changes": {"remaining_minutes": 30},
    }
    _, preview = propose(client, [draft(), action])
    client.patch(
        TASKS + "/" + task["id"],
        headers=csrf_headers(client),
        json={"expected_version": 1, "remaining_minutes": 40},
    )
    assert decide(client, preview).status_code == 409
    assert count(concurrent_engine, TaskModel) == 1
    _, fresh = propose(client, [action | {"expected_version": 2}])
    assert decide(client, fresh).json()["status"] == "applied"
    assert client.get(TASKS + "/" + task["id"]).json()["remaining_minutes"] == 30


def test_source_tool_loop_extracts_with_real_locator_and_survives_chat_cleanup(
    ai_client: TestClient, concurrent_engine: Engine
):
    client = ai_client
    app = cast(FastAPI, client.app)
    script(client, [draft()])
    block_id = str(uuid4())
    page = client.post(
        "/api/v1/notes/pages",
        headers=csrf_headers(client),
        json={
            "title": "Homework",
            "document": {
                "schema_version": 1,
                "blocks": [
                    {"id": block_id, "type": "text", "text": "Read chapter 3. The date is unclear."}
                ],
            },
        },
    ).json()
    query = {"page_id": page["id"], "block_id": block_id}
    reference = client.post(
        "/api/v1/ai/sources/read", headers=csrf_headers(client), json=query
    ).json()["sources"][0]
    action = draft(sources=[reference], uncertainties=["The deadline is unclear; left unset."])
    reader = SqlAlchemySourceReader(app.state.session_factory, app.state.academic_provider, 3600)
    checkpoints = InMemorySaver()

    @contextmanager
    def runners(run, journal):
        sources = SourceTools(reader, run.user_id, journal)
        model = FakeChatModel(
            responses=(
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "read_page", "args": query, "id": "read", "type": "tool_call"}
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "propose_actions",
                            "args": {"actions": [action]},
                            "id": "propose",
                            "type": "tool_call",
                        }
                    ],
                ),
            )
        )
        yield OfflineAgentRunner(
            model,
            [*sources.build_tools(), action_tool()],
            checkpoints,
            review_tools=frozenset({"propose_actions"}),
            sources=sources,
            journal=journal,
        )

    service = AiService(
        SqlAlchemyAiTransactions(app.state.session_factory),
        runners,
        actions=ActionService(SqlAlchemyActionTransactions(reader)),
    )
    app.dependency_overrides[get_ai] = lambda: service
    conversation = create(client)
    result = submit(client, conversation, "Extract tasks from the selected block")
    assert result.status_code == 200 and result.json()["status"] == "completed", result.text
    previews = client.get(f"/api/v1/ai/conversations/{conversation['id']}/proposals").json()
    assert previews and previews[0]["sources"][0]["locator"] == reference["locator"]
    assert decide(client, previews[0]).json()["status"] == "applied"
    assert (
        count(concurrent_engine, TaskOriginModel)
        == count(concurrent_engine, TaskPageLinkModel)
        == 1
    )
    client.delete("/api/v1/ai/conversations/" + conversation["id"], headers=csrf_headers(client))
    with Session(concurrent_engine) as database:
        origin = database.scalar(select(TaskOriginModel))
        assert origin and origin.provenance["sources"][0]["locator"] == reference["locator"]


def test_unread_or_changed_extraction_source_cannot_apply(
    ai_client: TestClient, concurrent_engine: Engine
):
    client = ai_client
    script(client, [draft()])
    page = client.post(
        "/api/v1/notes/pages", headers=csrf_headers(client), json={"title": "Homework"}
    ).json()
    ref = client.post(
        "/api/v1/ai/sources/read", headers=csrf_headers(client), json={"page_id": page["id"]}
    ).json()["sources"][0]
    # Directly forged tool arguments were not included in the runner's current read evidence.
    script(client, [draft(sources=[ref])])
    conversation = create(client)
    denied = submit(client, conversation)
    assert denied.status_code == 200 and denied.json()["status"] == "failed"
    assert count(concurrent_engine, TaskModel) == 0


def test_ai_plan_apply_uses_same_atomic_receipt(ai_client: TestClient, concurrent_engine: Engine):
    task = create_task(ai_client, remaining_minutes=90)
    plan = task_plan(ai_client, [task])
    _, preview = propose(
        ai_client,
        [{"operation": "task_plan_apply", "plan_id": plan["id"], "digest": plan["digest"]}],
    )
    assert preview["effects"][0]["after"]["sessions"] == plan["sessions"]
    first = decide(ai_client, preview)
    assert first.status_code == 200 and first.json()["status"] == "applied", first.text
    assert decide(ai_client, preview).json() == first.json()
    assert count(concurrent_engine, WorkSessionModel) == 2


def test_task_tools_scope_and_action_relationship_boundaries():
    identifier, other = uuid4(), uuid4()
    scope = SourceScope(task_ids=(identifier,), calendar=True)
    assert restrict_source_query(TaskRead(task_id=other), scope) is None
    restricted = restrict_source_query(TaskRead(), scope)
    assert isinstance(restricted, TaskRead) and restricted.task_ids == (identifier,)
    for actions in (
        [draft(parent_action=0)],
        [draft(predecessor_actions=[True])],
        [draft(estimate_kind="unknown")],
        [
            draft(
                sources=[
                    {
                        "source": "page",
                        "id": str(identifier),
                        "title": "Page",
                        "version": 1,
                        "locator": "search_snippet",
                    }
                ]
            )
        ],
    ):
        with pytest.raises(ValidationError):
            ActionBatch.model_validate({"actions": actions})


def test_plan_tool_returns_stable_preview_and_rejects_stale_cache(ai_client: TestClient):
    app = cast(FastAPI, ai_client.app)
    task = create_task(ai_client, remaining_minutes=90)
    preview = task_plan(ai_client, [task])
    with app.state.session_factory() as database:
        owner = database.scalar(select(TaskModel.user_id).where(TaskModel.id == UUID(task["id"])))
        assert owner
    reader = SqlAlchemySourceReader(app.state.session_factory, app.state.academic_provider, 3600)
    tools = SourceTools(reader, owner)
    request = {"request": preview["request"]}
    first = tools.read("preview_task_plan", request)
    assert first.status == "ok", first
    assert tools.read("preview_task_plan", request) == first
    ai_client.patch(
        TASKS + "/" + task["id"],
        headers=csrf_headers(ai_client),
        json={"expected_version": 1, "remaining_minutes": 30},
    )
    assert tools.read("preview_task_plan", request).status == "unavailable"


def test_empty_task_scope_preserves_existing_submission_digest_and_replay(ai_client: TestClient):
    conversation = create(ai_client)
    values: dict = {
        "submission_id": str(uuid4()),
        "message": "Synthetic scoped message",
        "source_scope": {"page_ids": [], "material_ids": [], "database_ids": [], "calendar": False},
    }
    path = f"/api/v1/ai/conversations/{conversation['id']}/messages"
    first = ai_client.post(path, headers=csrf_headers(ai_client), json=values)
    assert first.status_code == 200, first.text
    values["source_scope"]["task_ids"] = []
    replay = ai_client.post(path, headers=csrf_headers(ai_client), json=values)
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"], replay.text
