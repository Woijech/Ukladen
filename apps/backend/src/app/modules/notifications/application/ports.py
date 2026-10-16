from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.notifications.domain.notifications import Notification


class NotificationRepository(Protocol):
    """Durable owner-scoped inbox in the caller's transaction."""

    def create_once(self, notification: Notification) -> None: ...
    def get(self, user_id: UUID, notification_id: UUID) -> Notification | None: ...
    def list(
        self, user_id: UUID, unread_only: bool, limit: int, offset: int
    ) -> list[Notification]: ...
    def mark_read(self, user_id: UUID, notification_id: UUID, now: datetime) -> None: ...
