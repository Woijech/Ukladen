import logging
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.modules.users.application.ports import (
    AvatarImageProcessor,
    AvatarStorage,
    AvatarStorageUnavailable,
    ProfileRepository,
)
from app.modules.users.domain.avatar import AvatarNotFound
from app.modules.users.domain.profile import ProfileUnavailable, UserProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedAvatar:
    key: str
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class AvatarChange:
    profile: UserProfile
    previous_key: str | None


class AvatarService:
    """Callers own transactions and compensate storage only after rollback/commit."""

    def __init__(
        self,
        repository: ProfileRepository,
        storage: AvatarStorage,
        processor: AvatarImageProcessor,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.processor = processor

    def prepare(self, user_id: UUID, content: bytes, content_type: str) -> PreparedAvatar:
        return PreparedAvatar(
            f"avatars/{user_id}/{uuid4().hex}.png",
            self.processor.normalize(content, content_type),
        )

    def replace(self, user_id: UUID, avatar: PreparedAvatar) -> AvatarChange:
        current = self.repository.lock_active(user_id)
        if current is None:
            raise ProfileUnavailable()
        self.storage.put(avatar.key, avatar.content)
        profile = self.repository.update_avatar(user_id, avatar.key)
        if profile is None:
            raise ProfileUnavailable()
        return AvatarChange(profile, current.avatar_key)

    def get(self, user_id: UUID) -> bytes:
        # The lock prevents replacement cleanup from deleting an image during its read.
        profile = self.repository.lock_active(user_id)
        if profile is None:
            raise ProfileUnavailable()
        content = self.storage.get(profile.avatar_key) if profile.avatar_key else None
        if content is None:
            raise AvatarNotFound()
        return content

    def remove(self, user_id: UUID) -> str | None:
        profile = self.repository.lock_active(user_id)
        if profile is None:
            raise ProfileUnavailable()
        if profile.avatar_key is not None and self.repository.update_avatar(user_id, None) is None:
            raise ProfileUnavailable()
        return profile.avatar_key

    def cleanup(self, key: str | None) -> None:
        if key is None:
            return
        try:
            self.storage.delete(key)
        except AvatarStorageUnavailable:
            # ponytail: best-effort compensation; add durable cleanup if orphan recovery is needed.
            logger.warning("Avatar cleanup failed.", extra={"event": "avatar_cleanup_failed"})

    def cleanup_failed_upload(
        self, user_id: UUID, key: str, recovery_repository: ProfileRepository
    ) -> None:
        # A lost commit acknowledgement must not delete a successfully committed avatar.
        if recovery_repository.lock_avatar_key(user_id) != key:
            self.cleanup(key)
