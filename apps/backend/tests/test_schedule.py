from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from test_bsuir_academics import group_fixture
from test_bsuir_public_api import public_payload

from app.integrations.bsuir.public_api import normalize_payload
from app.modules.academics.domain.profile import AcademicProfile, AcademicProfileConflict
from app.modules.schedule.application.provider import Schedule, ScheduleProvider
from app.modules.schedule.application.schedule import AcademicProfileRequired, ScheduleService


@pytest.mark.parametrize("subgroup,expected", [(None, [0, 1, 2]), (1, [0, 1]), (2, [0, 2])])
def test_profile_selection_filters_current_next_and_exams(
    subgroup: int | None, expected: list[int]
) -> None:
    data = public_payload("group_schedule")
    lessons = [row for rows in data["schedules"].values() for row in rows]
    data.update(
        schedules={"Суббота": lessons}, nextSchedules={"Понедельник": lessons}, exams=lessons
    )
    original = TypeAdapter(Schedule).validate_python(normalize_payload(data), strict=True)
    provider = Mock(spec=ScheduleProvider, get_group_schedule=Mock(return_value=original))
    now = datetime.now(UTC)
    profile = AcademicProfile(uuid4(), group_fixture(), subgroup, now, now)
    selected = ScheduleService(provider).for_profile(profile)
    assert selected and selected.schedules and selected.next_schedules and selected.exams
    for rows in [
        selected.schedules["Суббота"],
        selected.next_schedules["Понедельник"],
        selected.exams,
    ]:
        assert sorted(row.subgroup for row in rows) == expected
        assert all(row.week_numbers and row.subject_full_name for row in rows)
    assert len(original.exams or []) == 3
    provider.get_group_schedule.assert_called_once_with("353501")


def test_profile_required_and_unpublished_or_replaced_group() -> None:
    provider = Mock(spec=ScheduleProvider)
    service = ScheduleService(provider)
    with pytest.raises(AcademicProfileRequired):
        service.for_profile(None)
    provider.get_group_schedule.assert_not_called()
    now = datetime.now(UTC)
    profile = AcademicProfile(uuid4(), group_fixture(), 1, now, now)
    provider.get_group_schedule.return_value = None
    assert service.for_profile(profile) is None
    data = public_payload("group_schedule")
    data["studentGroupDto"]["id"] = 999
    provider.get_group_schedule.return_value = TypeAdapter(Schedule).validate_python(
        normalize_payload(data)
    )
    with pytest.raises(AcademicProfileConflict):
        service.for_profile(profile)
