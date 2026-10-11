from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest

from app.modules.calendar.application.ports import PersonalCalendarEventRepository
from app.modules.calendar.application.service import MAX_PERIOD, PersonalEventService
from app.modules.calendar.domain.errors import EventNotFound, InvalidEventInput
from app.modules.calendar.domain.events import PersonalCalendarEvent
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable

NOW = datetime(2026, 10, 12, 8, tzinfo=UTC)


def event_for(user_id, **changes: object) -> PersonalCalendarEvent:
    event = PersonalCalendarEvent(
        id=uuid4(),
        user_id=user_id,
        title="Study session",
        description="Prepare for the next class.",
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=1),
        is_busy=True,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    return event


@pytest.fixture
def repository() -> Mock:
    return create_autospec(PersonalCalendarEventRepository, instance=True)


@pytest.fixture
def users() -> Mock:
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = True
    return users


@pytest.fixture
def service(repository, users) -> PersonalEventService:
    return PersonalEventService(repository, users)


def test_create_generates_identity_and_delegates(service, repository, users) -> None:
    user_id = uuid4()
    repository.create.side_effect = lambda owner, created: created
    created = service.create(
        user_id,
        {
            "title": "  Study session  ",
            "description": "  Prepare  ",
            "starts_at": NOW,
            "ends_at": NOW + timedelta(hours=1),
            "is_busy": False,
        },
    )
    users.is_active.assert_called_once_with(user_id)
    repository.create.assert_called_once()
    saved_user_id, event = repository.create.call_args.args
    assert saved_user_id == user_id
    assert event.user_id == user_id
    assert event.title == "Study session" and event.description == "Prepare"
    assert event.is_busy is False
    assert event.created_at == event.updated_at
    assert created == event


def test_create_defaults_busy_and_missing_description(service, repository) -> None:
    service.create(
        uuid4(),
        {"title": "Study session", "starts_at": NOW, "ends_at": NOW + timedelta(hours=1)},
    )
    _, event = repository.create.call_args.args
    assert event.is_busy is True and event.description is None


def test_create_requires_active_user(service, repository, users) -> None:
    users.is_active.return_value = False
    with pytest.raises(ProfileUnavailable):
        service.create(
            uuid4(),
            {"title": "Study session", "starts_at": NOW, "ends_at": NOW + timedelta(hours=1)},
        )
    repository.create.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [
        {"starts_at": NOW, "ends_at": NOW + timedelta(hours=1)},
        {"title": "Study session", "starts_at": NOW},
        {"title": " ", "starts_at": NOW, "ends_at": NOW + timedelta(hours=1)},
        {"title": "x" * 201, "starts_at": NOW, "ends_at": NOW + timedelta(hours=1)},
        {"title": "Study session", "starts_at": NOW, "ends_at": NOW},
        {"title": "Study session", "starts_at": NOW.replace(tzinfo=None)},
        {"title": "Study session", "starts_at": NOW, "ends_at": NOW, "unknown": 1},
        {},
    ],
)
def test_create_rejects_invalid_values(service, repository, values: dict) -> None:
    with pytest.raises(InvalidEventInput):
        service.create(uuid4(), values)
    repository.create.assert_not_called()


def test_get_returns_event_or_raises(service, repository) -> None:
    user_id, other_id = uuid4(), uuid4()
    event = event_for(user_id)
    repository.get.return_value = event
    assert service.get(user_id, event.id) == event
    repository.get.assert_called_with(user_id, event.id)
    repository.get.return_value = None
    for owner in (user_id, other_id):
        with pytest.raises(EventNotFound):
            service.get(owner, event.id)


def test_list_validates_period_and_delegates(service, repository) -> None:
    user_id = uuid4()
    event = event_for(user_id)
    repository.list_for_period.return_value = [event]
    assert service.list(user_id, NOW, NOW + timedelta(days=1)) == [event]
    repository.list_for_period.assert_called_with(user_id, NOW, NOW + timedelta(days=1))
    repository.list_for_period.reset_mock()

    for starts_at, ends_at in (
        (NOW.replace(tzinfo=None), NOW + timedelta(days=1)),
        (NOW, NOW),
        (NOW + timedelta(days=1), NOW),
        (NOW, NOW + MAX_PERIOD + timedelta(seconds=1)),
    ):
        with pytest.raises(InvalidEventInput):
            service.list(user_id, starts_at, ends_at)
    repository.list_for_period.assert_not_called()


def test_update_applies_partial_changes_and_preserves_fields(service, repository) -> None:
    user_id = uuid4()
    event = event_for(user_id)
    repository.get.return_value = event
    repository.update.side_effect = lambda owner, updated: updated

    updated = service.update(
        user_id, event.id, {"title": "  Renamed  ", "is_busy": False, "description": None}
    )

    repository.get.assert_called_with(user_id, event.id)
    saved_user_id, changed = repository.update.call_args.args
    assert saved_user_id == user_id
    assert changed.title == "Renamed" and changed.is_busy is False
    assert changed.description is None
    assert changed.starts_at == event.starts_at and changed.ends_at == event.ends_at
    assert changed.created_at == event.created_at and changed.id == event.id
    assert updated == changed


def test_update_requires_active_user(service, repository, users) -> None:
    users.is_active.return_value = False
    with pytest.raises(ProfileUnavailable):
        service.update(uuid4(), uuid4(), {"title": "Renamed"})
    repository.update.assert_not_called()


def test_update_rejects_missing_foreign_and_invalid_changes(service, repository) -> None:
    user_id, other_id = uuid4(), uuid4()
    event = event_for(user_id)
    repository.get.side_effect = lambda owner, event_id: event if owner == user_id else None
    with pytest.raises(EventNotFound):
        service.update(other_id, event.id, {"title": "Renamed"})
    repository.update.assert_not_called()

    repository.get.side_effect = None
    repository.get.return_value = None
    with pytest.raises(EventNotFound):
        service.update(user_id, event.id, {"title": "Renamed"})
    repository.update.assert_not_called()

    repository.get.return_value = event
    for changes in ({}, {"title": None}, {"ends_at": NOW}):
        with pytest.raises(InvalidEventInput):
            service.update(user_id, event.id, changes)
    repository.update.assert_not_called()
    assert repository.update.call_count == 0


def test_update_reports_missing_after_write(service, repository) -> None:
    user_id = uuid4()
    event = event_for(user_id)
    repository.get.return_value = event
    repository.update.return_value = None
    with pytest.raises(EventNotFound):
        service.update(user_id, event.id, {"title": "Renamed"})


def test_delete_requires_active_user_and_reports_missing(service, repository, users) -> None:
    user_id = uuid4()
    users.is_active.return_value = False
    with pytest.raises(ProfileUnavailable):
        service.delete(user_id, uuid4())
    repository.delete.assert_not_called()

    users.is_active.return_value = True
    repository.delete.return_value = True
    assert service.delete(user_id, uuid4()) is None
    repository.delete.return_value = False
    with pytest.raises(EventNotFound):
        service.delete(user_id, uuid4())
