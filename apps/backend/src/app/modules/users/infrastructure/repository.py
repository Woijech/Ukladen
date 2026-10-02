from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.users.application.ports import EmailAlreadyExists
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
