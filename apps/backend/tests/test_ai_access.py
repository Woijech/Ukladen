import json
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from test_ai_connections import configuration as configuration

from app.modules.ai.application.access import UnlimitedAiAccessPolicy
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.lifecycle import AgentRunners, AiService, AiTransactions
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.domain.connections import ConnectionUnavailable, UsageLimited
from app.modules.ai.domain.state import AiNotFound, Conversation, InvalidAiState
from app.modules.ai.infrastructure.connections import FileConnectionConfiguration


def service(configuration: FileConnectionConfiguration | None = None):
    repository = create_autospec(AiRepository, instance=True)
    transactions = create_autospec(AiTransactions, instance=True)
    transactions.return_value = nullcontext(repository)
    agent = AiService(
        transactions,
        create_autospec(AgentRunners, instance=True),
        connections=ConnectionAccess(configuration) if configuration else None,
    )
    return agent, repository


def test_default_uses_operator_key_without_personal_connection_and_demo_is_explicit(configuration):
    data = json.loads(configuration.path.read_text())
    data["entries"][0]["is_default"] = True
    configuration.path.write_text(json.dumps(data))
    agent, repository = service(configuration)
    owner = uuid4()
    chat = agent.create(owner, "Default")
    assert chat.offering_id == "flash" and chat.connection_id is None
    assert chat.provider == "openrouter"
    repository.get_connection.assert_not_called()
    assert agent.create(owner, "Offline", demo=True).provider == "fake"
    with pytest.raises(InvalidAiState):
        agent.create(owner, "Invalid", demo=True, offering_id="flash")
    (configuration.path.parent / "operator.key").unlink()
    with pytest.raises(ConnectionUnavailable):
        agent.create(owner, "No silent fallback")


def test_listed_models_preserve_restrictions_and_cannot_execute_until_enabled(configuration):
    owner, outsider = uuid4(), uuid4()
    data = json.loads(configuration.path.read_text())
    placeholder = data["entries"][0] | {
        "id": "planned",
        "enabled": False,
        "listed": True,
        "public": False,
        "allowed_user_ids": [str(owner)],
    }
    data["entries"].append(placeholder)
    configuration.path.write_text(json.dumps(data))
    options = configuration.model_options(owner)
    assert len(options) == 2 and options[0].operator_available
    assert not options[1].available and not options[1].operator_available
    assert len(configuration.model_options(outsider)) == 1
    assert "operator_key_file" not in options[0].model_dump()
    agent, _ = service(configuration)
    with pytest.raises(AiNotFound):
        agent.create(owner, "Unavailable", offering_id="planned")
    data["entries"][1]["enabled"] = True
    configuration.path.write_text(json.dumps(data))
    assert agent.create(owner, "Now available", offering_id="planned").offering_id == "planned"
    with pytest.raises(AiNotFound):
        agent.create(outsider, "Restricted", offering_id="planned")


def test_duplicate_catalog_defaults_fail_closed(configuration):
    data = json.loads(configuration.path.read_text())
    data["entries"][0]["is_default"] = True
    data["entries"].append(data["entries"][0] | {"id": "another"})
    configuration.path.write_text(json.dumps(data))
    with pytest.raises(ConnectionUnavailable):
        configuration.model_options(uuid4())


def test_usage_policy_is_unlimited_and_only_checks_new_admissions():
    agent, repository = service()
    owner = uuid4()
    chat = Conversation(id=uuid4(), user_id=owner, title="T", created_at=datetime.now(UTC))
    repository.get_conversation.return_value = chat
    repository.active_run.return_value = None
    repository.submission.return_value = None
    request = AgentInput(conversation_id=chat.id, message="Synthetic")
    status = agent.access_status(owner)
    assert status.plan == "free"
    assert status.monthly_request_limit is status.monthly_token_limit is None
    run, created = agent.admit(owner, request, uuid4())
    assert created
    for _ in range(24):
        run, created = agent.admit(owner, request, uuid4())
        assert created
    repository.create_run.reset_mock()

    class DenyPolicy(UnlimitedAiAccessPolicy):
        def admit(self, user_id, repository, now):
            raise UsageLimited()

    agent.access_policy = DenyPolicy()
    with pytest.raises(UsageLimited):
        agent.admit(owner, request, uuid4())
    repository.create_run.assert_not_called()
    repository.submission.return_value = run
    replay, created = agent.admit(owner, request, run.submission_id)
    assert replay == run and not created
