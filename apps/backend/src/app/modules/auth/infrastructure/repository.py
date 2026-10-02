from datetime import UTC, datetime
from ipaddress import ip_address
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.auth.domain.entities import AuthSession, OneTimeToken, TokenType
from app.modules.auth.infrastructure.orm import CredentialModel, OneTimeTokenModel, SessionModel


class SqlAlchemyCredentialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_password_hash(self, user_id: UUID) -> str | None:
        return self.session.scalar(
            select(CredentialModel.password_hash)
            .where(CredentialModel.user_id == user_id)
            .with_for_update()
        )


class SqlAlchemyRegistrationRepository:
    """Persist registration records without committing the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_credential(self, user_id: UUID, password_hash: str, created_at: datetime) -> None:
        self.session.add(
            CredentialModel(
                user_id=user_id,
                password_hash=password_hash,
                password_updated_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        self.session.flush()

    def create_one_time_token(self, token: OneTimeToken) -> None:
        self.session.add(
            OneTimeTokenModel(
                id=token.id,
                user_id=token.user_id,
                token_type=token.token_type,
                token_hash=token.token_hash,
                created_at=token.created_at,
                expires_at=token.expires_at,
                used_at=token.used_at,
            )
        )
        self.session.flush()


class SqlAlchemyEmailVerificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_token_hash(self, token_hash: str) -> OneTimeToken | None:
        row = self.session.scalar(
            select(OneTimeTokenModel)
            .where(
                OneTimeTokenModel.token_hash == token_hash,
                OneTimeTokenModel.token_type == TokenType.EMAIL_VERIFICATION,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        return OneTimeToken(
            id=row.id,
            user_id=row.user_id,
            token_type=TokenType.EMAIL_VERIFICATION,
            token_hash=row.token_hash,
            created_at=row.created_at,
            expires_at=row.expires_at,
            used_at=row.used_at,
        )

    def mark_used(self, token_id: UUID, used_at: datetime) -> None:
        self.session.execute(
            update(OneTimeTokenModel)
            .where(OneTimeTokenModel.id == token_id)
            .values(used_at=used_at)
        )


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
            .with_for_update()
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

    def revoke(self, session_id: UUID) -> str | None:
        return self.session.scalar(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(revoked_at=func.coalesce(SessionModel.revoked_at, datetime.now(UTC)))
            .returning(SessionModel.token_hash)
        )

    def revoke_all_for_user(self, user_id: UUID) -> list[str]:
        return list(
            self.session.scalars(
                update(SessionModel)
                .where(SessionModel.user_id == user_id)
                .values(revoked_at=func.coalesce(SessionModel.revoked_at, datetime.now(UTC)))
                .returning(SessionModel.token_hash)
            )
        )
