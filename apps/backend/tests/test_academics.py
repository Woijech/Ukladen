from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest

from app.modules.academics.application.ports import (
    AcademicProfileRepository,
    AcademicProvider,
    AcademicProviderUnavailable,
)
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.domain.profile import (
    AcademicProfile,
    AcademicProfileConflict,
    GroupContext,
    InvalidAcademicSelection,
    UniversityGroup,
    normalize_academic_changes,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable

GROUP = UniversityGroup(24066, "353501", 20026, "Faculty", "F", 20657, "Speciality", "S", 4, 1)
OTHER = replace(GROUP, id=24684, name="310101")
USER_ID = uuid4()
NOW = datetime.now(UTC)
PROFILE = AcademicProfile(USER_ID, GROUP, 1, NOW, NOW)


@pytest.fixture
def repository() -> Mock:
    repository = create_autospec(AcademicProfileRepository, instance=True)
    repository.get.return_value = PROFILE
    repository.save.side_effect = lambda user_id, group, subgroup: replace(
        PROFILE, user_id=user_id, group=group, subgroup=subgroup
    )
    return repository


@pytest.fixture
def users() -> Mock:
    users = create_autospec(UserAuthentication, instance=True)
    users.is_active.return_value = users.lock_active.return_value = True
    return users


@pytest.fixture
def provider() -> Mock:
    provider = create_autospec(AcademicProvider, instance=True)
    provider.list_groups.return_value = [GROUP, OTHER]
    provider.get_context.side_effect = lambda group: GroupContext(group, True, (1, 2))
    return provider


@pytest.fixture
def service(repository: Mock, users: Mock, provider: Mock) -> AcademicService:
    return AcademicService(repository, users, provider)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"group_id": None},
        {"group_id": True},
        {"group_id": "24066"},
        {"subgroup": 0},
        {"subgroup": -1},
        {"subgroup": True},
        {"semester": 1},
        {"user_id": str(USER_ID)},
        {"group_id": 2**63},
    ],
)
def test_invalid_changes(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidAcademicSelection):
        normalize_academic_changes(changes)


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"group_id": GROUP.id}, 1),
        ({"subgroup": None}, None),
        ({"subgroup": 2}, 2),
        ({"group_id": OTHER.id}, None),
        ({"group_id": OTHER.id, "subgroup": 2}, 2),
    ],
)
def test_selection_omission_null_and_group_changes(
    service: AcademicService, users: Mock, changes: dict[str, object], expected: int | None
) -> None:
    prepared = service.prepare(PROFILE, changes)
    result = service.update(USER_ID, prepared)
    assert result.subgroup == expected and result.user_id == USER_ID
    assert result.group.id == changes.get("group_id", GROUP.id)
    users.lock_active.assert_called_once_with(USER_ID)


def test_missing_profile_can_be_created_only_with_group(
    service: AcademicService, repository: Mock
) -> None:
    repository.get.return_value = None
    assert service.get(USER_ID) is None
    with pytest.raises(InvalidAcademicSelection):
        service.prepare(None, {"subgroup": None})
    prepared = service.prepare(None, {"group_id": GROUP.id})
    assert service.update(USER_ID, prepared).subgroup is None


@pytest.mark.parametrize(
    "changes", [{"group_id": 1}, {"subgroup": 3}, {"group_id": OTHER.id, "subgroup": 3}]
)
def test_invalid_catalogue_selections(
    service: AcademicService, repository: Mock, changes: dict[str, object]
) -> None:
    with pytest.raises(InvalidAcademicSelection):
        service.prepare(PROFILE, changes)
    repository.save.assert_not_called()


def test_reads_and_clear_do_not_need_iis(service: AcademicService, provider: Mock) -> None:
    provider.list_groups.side_effect = AcademicProviderUnavailable()
    provider.get_context.side_effect = AcademicProviderUnavailable()
    assert service.get(USER_ID) == PROFILE
    assert service.update(USER_ID, service.prepare(PROFILE, {"subgroup": None})).subgroup is None
    provider.list_groups.assert_not_called()
    provider.get_context.assert_not_called()
    with pytest.raises(AcademicProviderUnavailable):
        service.prepare(PROFILE, {"group_id": GROUP.id})


def test_canonical_eligibility_and_concurrent_group_change(
    service: AcademicService, repository: Mock, users: Mock
) -> None:
    prepared = service.prepare(PROFILE, {"subgroup": 2})
    repository.get.return_value = replace(PROFILE, group=OTHER)
    with pytest.raises(AcademicProfileConflict):
        service.update(USER_ID, prepared)
    repository.save.assert_not_called()
    users.is_active.return_value = users.lock_active.return_value = False
    with pytest.raises(ProfileUnavailable):
        service.get(USER_ID)
    with pytest.raises(ProfileUnavailable):
        service.update(USER_ID, prepared)
