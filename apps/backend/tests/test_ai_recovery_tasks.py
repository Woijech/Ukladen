import importlib
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from test_auth_http import settings as settings

from app.core import config
from app.core.config import Settings
from app.modules.ai.domain.state import AiPersistenceUnavailable


@pytest.fixture
def tasks(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> ModuleType:
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    return importlib.import_module("app.modules.ai.infrastructure.tasks")


def test_disabled_recovery_does_not_open_database(tasks: ModuleType) -> None:
    with (
        patch.object(
            tasks,
            "get_settings",
            return_value=SimpleNamespace(ai_enabled=False, ai_retention_enabled=False),
        ),
        patch.object(tasks, "create_database_engine") as create,
    ):
        tasks.reconcile.run()
        create.assert_not_called()


def test_recovery_storage_failure_is_sanitized_and_closes_engine(tasks: ModuleType) -> None:
    engine = Mock()
    with (
        patch.object(tasks, "get_settings", return_value=SimpleNamespace(ai_enabled=True)),
        patch.object(tasks, "create_database_engine", return_value=engine),
        patch.object(tasks, "create_session_factory"),
        patch.object(tasks, "reconcile_runs", side_effect=RuntimeError("private storage detail")),
    ):
        with pytest.raises(AiPersistenceUnavailable, match="^AI recovery is unavailable.$"):
            tasks.reconcile.run()
    engine.dispose.assert_called_once()


def test_retention_can_continue_with_chat_disabled(tasks: ModuleType) -> None:
    engine = Mock()
    with (
        patch.object(
            tasks,
            "get_settings",
            return_value=SimpleNamespace(ai_enabled=False, ai_retention_enabled=True),
        ),
        patch.object(tasks, "create_database_engine", return_value=engine),
        patch.object(tasks, "create_session_factory") as sessions,
        patch.object(tasks, "reconcile_runs") as recover,
        patch.object(tasks, "purge_expired") as purge,
    ):
        tasks.reconcile.run()
        recover.assert_called_once_with(sessions.return_value)
        purge.assert_called_once_with(sessions.return_value)
    engine.dispose.assert_called_once()
