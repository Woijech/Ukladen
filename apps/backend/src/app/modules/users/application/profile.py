from collections.abc import Mapping
from uuid import UUID

from app.modules.users.application.ports import ProfileRepository
from app.modules.users.domain.profile import (
    ProfileUnavailable,
    UserProfile,
    normalize_profile_changes,
)


class ProfileService:
    """Callers own transactions and must commit before returning success."""

    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    def get(self, user_id: UUID) -> UserProfile:
        profile = self.repository.get_active(user_id)
        if profile is None:
            raise ProfileUnavailable()
        return profile

    def update(self, user_id: UUID, changes: Mapping[str, object]) -> UserProfile:
        profile = self.repository.update_active(user_id, normalize_profile_changes(changes))
        if profile is None:
            raise ProfileUnavailable()
        return profile
