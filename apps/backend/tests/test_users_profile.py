from datetime import UTC, datetime
from unittest.mock import create_autospec
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.modules.users.application.ports import ProfileRepository
from app.modules.users.application.profile import ProfileService
from app.modules.users.domain.profile import (
    InvalidProfile,
    ProfileUnavailable,
    UserProfile,
    normalize_profile_changes,
)
from app.modules.users.presentation.schemas import ProfilePatch, ProfileResponse


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"display_name": ""},
        {"display_name": " \t\n\u00a0"},
        {"display_name": "x" * 101},
        {"display_name": 1},
        {"timezone": None},
        {"timezone": ""},
        {"timezone": "Mars/Olympus"},
        {"timezone": "../UTC"},
        {"timezone": "/etc/passwd"},
        {"timezone": " UTC "},
        {"timezone": 1},
        {"locale": None},
        {"locale": ""},
        {"locale": "fr"},
        {"locale": "RU"},
        {"locale": 1},
        {"email": "attacker@example.com"},
        {"id": str(uuid4())},
        {"user_id": str(uuid4())},
        {"email_verified_at": None},
        {"status": "active"},
        {"created_at": None},
        {"updated_at": None},
        {"password": "secret"},
        {"preferences": {}},
        {"display_name": "Alex", "unknown": "value"},
    ],
)
def test_invalid_changes_are_rejected_at_both_boundaries(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProfilePatch.model_validate(changes)
    with pytest.raises(InvalidProfile):
        normalize_profile_changes(changes)
    repository = create_autospec(ProfileRepository, instance=True)
    with pytest.raises(InvalidProfile):
        ProfileService(repository).update(uuid4(), changes)
    repository.update_active.assert_not_called()


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"display_name": " \tAlex\n "}, {"display_name": "Alex"}),
        ({"display_name": " \u00a0" + "я" * 100 + " "}, {"display_name": "я" * 100}),
        ({"display_name": None}, {"display_name": None}),
        ({"timezone": "Europe/Minsk"}, {"timezone": "Europe/Minsk"}),
        ({"timezone": "America/New_York"}, {"timezone": "America/New_York"}),
        ({"timezone": "UTC"}, {"timezone": "UTC"}),
        ({"locale": "en"}, {"locale": "en"}),
        ({"locale": "ru"}, {"locale": "ru"}),
        (
            {"display_name": " Alex ", "timezone": "Europe/Minsk", "locale": "en"},
            {"display_name": "Alex", "timezone": "Europe/Minsk", "locale": "en"},
        ),
    ],
)
def test_normalization_and_omission(
    changes: dict[str, object], expected: dict[str, object]
) -> None:
    patch = ProfilePatch.model_validate(changes)
    assert patch.model_dump(exclude_unset=True) == expected
    assert normalize_profile_changes(changes) == expected
    repository = create_autospec(ProfileRepository, instance=True)
    user_id = uuid4()
    ProfileService(repository).update(user_id, changes)
    repository.update_active.assert_called_once_with(user_id, expected)


def test_service_rechecks_canonical_eligibility() -> None:
    repository = create_autospec(ProfileRepository, instance=True)
    repository.get_active.return_value = None
    repository.update_active.return_value = None
    service = ProfileService(repository)
    user_id = uuid4()
    with pytest.raises(ProfileUnavailable):
        service.get(user_id)
    with pytest.raises(ProfileUnavailable):
        service.update(user_id, {"locale": "en"})
    repository.get_active.assert_called_once_with(user_id)
    repository.update_active.assert_called_once_with(user_id, {"locale": "en"})


def test_timezone_data_and_aware_response() -> None:
    for name in ("UTC", "Europe/Minsk", "America/New_York", "Asia/Tokyo"):
        assert ZoneInfo(name).key == name
    now = datetime.now(UTC)
    profile = UserProfile(
        uuid4(), "student@example.com", None, "active", None, "UTC", "ru", now, now
    )
    assert ProfileResponse.model_validate(profile).created_at.utcoffset() is not None
    with pytest.raises(ValidationError):
        ProfileResponse.model_validate(profile.__dict__ | {"created_at": now.replace(tzinfo=None)})
