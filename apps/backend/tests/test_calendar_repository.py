from datetime import UTC, datetime, timedelta
from unittest.mock import create_autospec
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.modules.calendar.infrastructure.repository import SqlAlchemyPersonalCalendarEventRepository

NOW = datetime(2026, 10, 9, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    "starts_at,ends_at",
    [
        (NOW.replace(tzinfo=None), NOW + timedelta(hours=1)),
        (NOW, (NOW + timedelta(hours=1)).replace(tzinfo=None)),
        (NOW, NOW),
        (NOW + timedelta(hours=1), NOW),
        (
            datetime(2026, 10, 25, 2, 45, tzinfo=ZoneInfo("Europe/Berlin"), fold=1),
            datetime(2026, 10, 25, 2, 50, tzinfo=ZoneInfo("Europe/Berlin"), fold=0),
        ),
    ],
)
def test_invalid_period_rejected_before_query(starts_at: datetime, ends_at: datetime) -> None:
    session = create_autospec(Session, instance=True)
    repository = SqlAlchemyPersonalCalendarEventRepository(session)
    with pytest.raises(ValueError):
        repository.list_for_period(uuid4(), starts_at, ends_at)
    session.scalars.assert_not_called()
