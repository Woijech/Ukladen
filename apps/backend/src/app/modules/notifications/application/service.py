from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.modules.notifications.application.ports import NotificationRepository
from app.modules.notifications.domain.notifications import (
    InvalidNotificationInput,
    Notification,
    NotificationNotFound,
)
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        users: UserAuthentication,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.now = repository, users, now

    def require_user(self, user_id: UUID, *, write: bool = False) -> None:
        active = self.users.lock_active(user_id) if write else self.users.is_active(user_id)
        if not active:
            raise ProfileUnavailable()

    def get(self, user_id: UUID, notification_id: UUID) -> Notification:
        self.require_user(user_id)
        notification = self.repository.get(user_id, notification_id)
        if notification is None:
            raise NotificationNotFound()
        return notification

    def list(
        self, user_id: UUID, unread_only: bool = False, limit: int = 100, offset: int = 0
    ) -> list[Notification]:
        self.require_user(user_id)
        if (
            type(unread_only) is not bool
            or type(limit) is not int
            or type(offset) is not int
            or not (1 <= limit <= 200 and 0 <= offset <= 2**31 - 1)
        ):
            raise InvalidNotificationInput()
        return self.repository.list(user_id, unread_only, limit, offset)

    def mark_read(self, user_id: UUID, notification_id: UUID) -> Notification:
        self.require_user(user_id, write=True)
        self.repository.mark_read(user_id, notification_id, self.now())
        return self.get(user_id, notification_id)

    def publish(self, notification: Notification) -> None:
        """Internal application operation; no HTTP endpoint accepts notification payloads."""
        self.require_user(notification.user_id, write=True)
        self.repository.create_once(notification)
