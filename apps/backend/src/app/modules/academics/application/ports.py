from typing import Protocol
from uuid import UUID

from app.modules.academics.domain.profile import AcademicProfile, GroupContext, UniversityGroup


class AcademicProviderUnavailable(Exception):
    """IIS could not provide a valid response; do not expose upstream details."""


class AcademicProvider(Protocol):
    def list_groups(self) -> list[UniversityGroup]: ...

    def get_context(self, group: UniversityGroup) -> GroupContext: ...


class AcademicProfileRepository(Protocol):
    """All operations participate in the caller's transaction; never commit."""

    def get(self, user_id: UUID) -> AcademicProfile | None: ...

    def save(
        self, user_id: UUID, group: UniversityGroup, subgroup: int | None
    ) -> AcademicProfile: ...
