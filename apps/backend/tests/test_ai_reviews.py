from datetime import UTC, datetime
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from test_ai_persistence import ai_database as ai_database
from test_ai_persistence import migration_config, seed

from alembic import command
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.application.reviews import (
    ReviewConfiguration,
    ReviewSettingsService,
    SavedReviewSettings,
    review_slots,
)
from app.modules.ai.domain.connections import ModelSelection
from app.modules.ai.domain.state import AiConflict
from app.modules.ai.infrastructure.review_settings import SqlAlchemyReviewSettings
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def test_activation_requires_explicit_model_and_review_type():
    assert not ReviewConfiguration().enabled
    for values in (
        {"enabled": True},
        {"connection_id": uuid4()},
        {"daily_time": "24:00"},
        {"weekly_day": 7},
        {
            "enabled": True,
            "offering_id": "flash",
            "daily": False,
            "weekly": False,
            "warnings": False,
        },
    ):
        with pytest.raises(ValidationError):
            ReviewConfiguration.model_validate(values)


def test_local_slots_catch_up_across_dst_and_do_not_repeat_hours():
    configuration = ReviewConfiguration(enabled=True, offering_id="flash", daily_time="02:30")

    def slots(value):
        return review_slots(configuration, datetime.fromisoformat(value), "Europe/Berlin")

    assert "daily" not in slots("2026-03-29T00:59:00+00:00")
    assert slots("2026-03-29T01:00:00+00:00")["daily"] == "2026-03-29"
    assert slots("2026-10-25T00:30:00+00:00") == slots("2026-10-25T01:30:00+00:00")
    assert slots("2026-10-29T14:00:00+00:00")["weekly"] == "2026-10-26"
    assert review_slots(ReviewConfiguration(), datetime.now(UTC), "Europe/Minsk") == {}
    with pytest.raises(ValueError):
        review_slots(configuration, datetime(2026, 10, 29), "Europe/Minsk")


def test_native_settings_owner_versions_selected_connection_and_preserving_migration(
    ai_database: Engine,
):
    chat, other = seed(ai_database)
    access = create_autospec(ConnectionAccess, instance=True)
    selection = ModelSelection(offering_id="flash", offering_version=3, connection_id=None)
    offering = type("Offering", (), {"tools": True})()
    access.select.return_value = selection, offering
    configuration = ReviewConfiguration(enabled=True, offering_id="flash")
    with Session(ai_database) as database, database.begin():
        repository = SqlAlchemyReviewSettings(database)
        service = ReviewSettingsService(repository, SqlAlchemyUserAuthentication(database))
        assert service.get(chat.user_id) == SavedReviewSettings()
        saved = service.save(
            chat.user_id,
            configuration,
            0,
            connections=access,
            ai=create_autospec(AiRepository, instance=True),
        )
        assert saved.version == 1 and saved.offering_version == 3
        assert service.get(other) == SavedReviewSettings()
        with pytest.raises(AiConflict):
            service.save(
                chat.user_id,
                configuration,
                0,
                connections=access,
                ai=create_autospec(AiRepository, instance=True),
            )
    with Session(ai_database) as database, database.begin():
        service = ReviewSettingsService(
            SqlAlchemyReviewSettings(database), SqlAlchemyUserAuthentication(database)
        )
        assert service.get(chat.user_id).configuration == configuration
        disabled = service.save(
            chat.user_id,
            ReviewConfiguration(),
            1,
            connections=access,
            ai=create_autospec(AiRepository, instance=True),
        )
        assert disabled.version == 2 and disabled.offering_version is None
    with ai_database.begin() as database:
        command.check(migration_config(database))
        with pytest.raises(RuntimeError, match="Cannot discard"), database.begin_nested():
            command.downgrade(migration_config(database), "0038_ai_action_revisions")


def test_disabling_reviews_does_not_require_a_working_connection():
    from app.modules.ai.application.reviews import ReviewSettingsRepository
    from app.modules.users.application.ports import UserAuthentication

    repository = create_autospec(ReviewSettingsRepository, instance=True)
    users = create_autospec(UserAuthentication, instance=True)
    users.lock_active.return_value = True
    enabled = ReviewConfiguration(enabled=True, offering_id="flash")
    repository.get.return_value = SavedReviewSettings(enabled, 1, 3)
    access = create_autospec(ConnectionAccess, instance=True)
    access.select.side_effect = AssertionError("Disabling must not inspect credentials.")
    saved = ReviewSettingsService(repository, users).save(
        uuid4(),
        enabled.model_copy(update={"enabled": False}),
        1,
        connections=access,
        ai=create_autospec(AiRepository, instance=True),
    )
    assert not saved.configuration.enabled and saved.version == 2
    access.select.assert_not_called()
