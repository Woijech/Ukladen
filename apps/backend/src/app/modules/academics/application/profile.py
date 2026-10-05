from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.academics.application.ports import AcademicProfileRepository, AcademicProvider
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


@dataclass(frozen=True)
class PreparedAcademicUpdate:
    changes: dict[str, int | None]
    group: UniversityGroup
    expected_group_id: int | None


class AcademicService:
    """Prepare outside transactions; read/write in caller-owned transactions."""

    def __init__(
        self,
        repository: AcademicProfileRepository,
        users: UserAuthentication,
        provider: AcademicProvider,
    ) -> None:
        self.repository = repository
        self.users = users
        self.provider = provider

    def get(self, user_id: UUID) -> AcademicProfile | None:
        if not self.users.is_active(user_id):
            raise ProfileUnavailable()
        return self.repository.get(user_id)

    def get_group(self, group_id: int) -> UniversityGroup:
        group = next((g for g in self.provider.list_groups() if g.id == group_id), None)
        if group is None:
            raise InvalidAcademicSelection("Invalid group selection.")
        return group

    def get_context(self, group_id: int) -> GroupContext:
        return self.provider.get_context(self.get_group(group_id))

    def prepare(
        self, current: AcademicProfile | None, changes: Mapping[str, object]
    ) -> PreparedAcademicUpdate:
        values = normalize_academic_changes(changes)
        group_id = values.get("group_id")
        if group_id is not None:
            group = self.get_group(group_id)
        elif current is not None:
            group = current.group
        else:
            raise InvalidAcademicSelection("Select a group before setting a subgroup.")
        subgroup = values.get("subgroup")
        if subgroup is not None:
            if group_id is None:
                group = self.get_group(group.id)
            if subgroup not in self.provider.get_context(group).subgroups:
                raise InvalidAcademicSelection("Invalid subgroup selection.")
        return PreparedAcademicUpdate(values, group, current.group.id if current else None)

    def update(self, user_id: UUID, prepared: PreparedAcademicUpdate) -> AcademicProfile:
        if not self.users.lock_active(user_id):
            raise ProfileUnavailable()
        current = self.repository.get(user_id)
        if "group_id" not in prepared.changes:
            if (current.group.id if current else None) != prepared.expected_group_id:
                raise AcademicProfileConflict()
        subgroup = prepared.changes.get("subgroup")
        if "subgroup" not in prepared.changes and current and current.group.id == prepared.group.id:
            subgroup = current.subgroup
        return self.repository.save(user_id, prepared.group, subgroup)
