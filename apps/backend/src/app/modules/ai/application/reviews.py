"""Opt-in review settings and local-time schedule; no provider dispatch."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.persistence import AiRepository
from app.modules.ai.application.source_queries import SourceScope
from app.modules.ai.domain.state import AiConflict, InvalidAiState
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable

ReviewKind = Literal["daily", "weekly", "warnings"]
CLOCK = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"


class ReviewConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    daily: bool = True
    weekly: bool = True
    warnings: bool = True
    materials: bool = True
    daily_time: str = Field(default="09:00", pattern=CLOCK)
    weekly_time: str = Field(default="09:00", pattern=CLOCK)
    weekly_day: int = Field(default=0, ge=0, le=6)
    offering_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    connection_id: UUID | None = None
    source_scope: SourceScope | None = None

    @model_validator(mode="after")
    def explicit_activation(self):
        if self.enabled and (
            not self.offering_id or not (self.daily or self.weekly or self.warnings)
        ):
            raise ValueError("Enabled reviews require a model and at least one review type.")
        if self.connection_id is not None and self.offering_id is None:
            raise ValueError("A personal connection requires an explicit model.")
        if self.source_scope is not None:
            scope = self.source_scope
            if (
                scope.database_ids
                or len(scope.page_ids) + len(scope.material_ids) + len(scope.task_ids) > 100
            ):
                raise ValueError("Review scopes support at most 100 tasks, pages and materials.")
        return self


@dataclass(frozen=True)
class SavedReviewSettings:
    configuration: ReviewConfiguration = ReviewConfiguration()
    version: int = 0
    offering_version: int | None = None


class ReviewSettingsRepository(Protocol):
    def get(self, user_id: UUID) -> SavedReviewSettings: ...
    def save(self, user_id: UUID, value: SavedReviewSettings, expected_version: int) -> None: ...


class ReviewSettingsService:
    def __init__(self, repository: ReviewSettingsRepository, users: UserAuthentication):
        self.repository, self.users = repository, users

    def get(self, user_id: UUID) -> SavedReviewSettings:
        if not self.users.is_active(user_id):
            raise ProfileUnavailable()
        return self.repository.get(user_id)

    def save(
        self,
        user_id: UUID,
        configuration: ReviewConfiguration,
        expected_version: int,
        *,
        connections: ConnectionAccess | None,
        ai: AiRepository,
    ) -> SavedReviewSettings:
        if not self.users.lock_active(user_id):
            raise ProfileUnavailable()
        current = self.repository.get(user_id)
        if type(expected_version) is not int or expected_version != current.version:
            raise AiConflict("Review settings changed.")
        offering_version = (
            current.offering_version
            if configuration.offering_id == current.configuration.offering_id
            else None
        )
        if configuration.enabled and configuration.offering_id is not None:
            if connections is None:
                raise InvalidAiState("Select a supported model connection.")
            selection, offering = connections.select(
                ai, user_id, configuration.offering_id, configuration.connection_id
            )
            if not offering.tools:
                raise InvalidAiState("Select a workspace-capable model.")
            offering_version = selection.offering_version
        value = SavedReviewSettings(configuration, current.version + 1, offering_version)
        self.repository.save(user_id, value, expected_version)
        return value


def review_slots(
    configuration: ReviewConfiguration, now: datetime, timezone: str
) -> dict[ReviewKind, str]:
    """One local-day/week slot; DST gaps catch up and repeated hours cannot duplicate it."""
    if not configuration.enabled:
        return {}
    if now.utcoffset() is None:
        raise ValueError("An aware review clock is required.")
    local = now.astimezone(ZoneInfo(timezone))
    clock = local.strftime("%H:%M")
    result: dict[ReviewKind, str] = {}
    if configuration.daily and clock >= configuration.daily_time:
        result["daily"] = local.date().isoformat()
    week = local.date() - timedelta(days=local.weekday())
    due = week + timedelta(days=configuration.weekly_day)
    if configuration.weekly and (
        local.date() > due or (local.date() == due and clock >= configuration.weekly_time)
    ):
        result["weekly"] = week.isoformat()
    if configuration.warnings:
        result["warnings"] = "changed-state"
    return result
