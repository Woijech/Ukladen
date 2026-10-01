from datetime import UTC, datetime
from ipaddress import ip_address
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.infrastructure.orm import SessionModel


class SqlAlchemySessionRepository:
    """Persist domain sessions within a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, session: AuthSession) -> None:
        self.session.add(
            SessionModel(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                user_agent=session.user_agent,
                ip_address=str(session.ip_address) if session.ip_address is not None else None,
            )
        )
        self.session.flush()

    def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        row = self.session.scalar(
            select(SessionModel)
            .where(SessionModel.token_hash == token_hash)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        return AuthSession(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            user_agent=row.user_agent,
            ip_address=ip_address(row.ip_address) if row.ip_address is not None else None,
        )

    def revoke(self, session_id: UUID) -> None:
        self.session.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id, SessionModel.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    def revoke_all_for_user(self, user_id: UUID) -> None:
        self.session.execute(
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
