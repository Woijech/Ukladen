from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.users.application.ports import EmailAlreadyExists
from app.modules.users.domain.profile import UserProfile
from app.modules.users.infrastructure.orm import UserModel


class SqlAlchemyUserRegistration:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, email: str) -> UUID:
        user_id = self.session.scalar(
            insert(UserModel)
            .values(email=email)
            .on_conflict_do_nothing(index_elements=[func.lower(UserModel.email)])
            .returning(UserModel.id)
        )
        if user_id is None:
            raise EmailAlreadyExists("Email is already registered.")
        return user_id


class SqlAlchemyEmailVerifier:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_unverified_email(self, user_id: UUID) -> str | None:
        return self.session.scalar(
            select(UserModel.email)
            .where(
                UserModel.id == user_id,
                UserModel.status == "active",
                UserModel.email_verified_at.is_(None),
            )
            .with_for_update()
        )

    def mark_verified(self, user_id: UUID, verified_at: datetime) -> bool:
        return (
            self.session.scalar(
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(email_verified_at=func.coalesce(UserModel.email_verified_at, verified_at))
                .returning(UserModel.id)
            )
            is not None
        )


class SqlAlchemyUserAuthentication:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_id_by_email(self, email: str) -> UUID | None:
        return self.session.scalar(
            select(UserModel.id)
            .where(func.lower(UserModel.email) == email, UserModel.status == "active")
            .with_for_update()
        )

    def lock_active(self, user_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(UserModel.id)
                .where(UserModel.id == user_id, UserModel.status == "active")
                .with_for_update()
            )
            is not None
        )

    def is_active(self, user_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(UserModel.id).where(UserModel.id == user_id, UserModel.status == "active")
            )
            is not None
        )


class SqlAlchemyProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, user_id: UUID) -> UserProfile | None:
        row = self.session.scalar(
            select(UserModel)
            .where(UserModel.id == user_id, UserModel.status == "active")
            .execution_options(populate_existing=True)
        )
        return self._to_profile(row)

    def update_active(self, user_id: UUID, changes: dict[str, str | None]) -> UserProfile | None:
        row = self.session.scalar(
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.status == "active")
            .values(**changes, updated_at=func.clock_timestamp())
            .returning(UserModel)
            .execution_options(populate_existing=True)
        )
        return self._to_profile(row)

    def lock_active(self, user_id: UUID) -> UserProfile | None:
        row = self.session.scalar(
            select(UserModel)
            .where(UserModel.id == user_id, UserModel.status == "active")
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self._to_profile(row)

    def update_avatar(self, user_id: UUID, key: str | None) -> UserProfile | None:
        row = self.session.scalar(
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.status == "active")
            .values(avatar_key=key, updated_at=func.clock_timestamp())
            .returning(UserModel)
            .execution_options(populate_existing=True)
        )
        return self._to_profile(row)

    def lock_avatar_key(self, user_id: UUID) -> str | None:
        return self.session.scalar(
            select(UserModel.avatar_key).where(UserModel.id == user_id).with_for_update()
        )

    @staticmethod
    def _to_profile(row: UserModel | None) -> UserProfile | None:
        if row is None:
            return None
        return UserProfile(
            id=row.id,
            email=row.email,
            email_verified_at=row.email_verified_at,
            status=row.status,
            display_name=row.display_name,
            timezone=row.timezone,
            locale=row.locale,
            created_at=row.created_at,
            updated_at=row.updated_at,
            avatar_key=row.avatar_key,
        )
