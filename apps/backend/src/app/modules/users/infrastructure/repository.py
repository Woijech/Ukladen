from datetime import datetime
from uuid import UUID

from sqlalchemy import func, update
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
