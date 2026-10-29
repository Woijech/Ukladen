from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.modules.ai.application.review_evidence import digest
from app.modules.ai.application.reviews import ReviewConfiguration
from app.modules.ai.domain.state import AiConflict, AiNotFound
from app.modules.ai.infrastructure.actions import SqlAlchemyActionTransactions
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.review_collection import collect_review
from app.modules.ai.infrastructure.review_models import ReviewModel


class ReviewReports:
    def __init__(self, service, reader):
        self.service, self.reader = service, reader
        self.transactions = SqlAlchemyActionTransactions(reader)

    def read(self, context, user_id: UUID, identifier: UUID):
        repository = context.ai
        assert isinstance(repository, SqlAlchemyAiRepository)
        row = repository.session.scalar(
            select(ReviewModel).where(ReviewModel.user_id == user_id, ReviewModel.id == identifier)
        )
        if row is None or row.expires_at <= self.service.now():
            raise AiNotFound()
        self.service.conversation(repository, user_id, row.conversation_id)
        messages = repository.messages(user_id, row.conversation_id, 0, 1)
        message = messages[0] if messages and row.status == "completed" else None
        result = dict(
            id=row.id,
            kind=row.kind,
            status=row.status,
            created_at=row.created_at,
            expires_at=row.expires_at,
            content=message.content if message else None,
            sources=message.sources if message else (),
            stale=False,
        )
        if message is not None:
            try:
                current = collect_review(
                    repository.session,
                    self.reader,
                    user_id,
                    ReviewConfiguration.model_validate(row.configuration),
                    row.created_at,
                )
                if digest(current.payload()) != row.snapshot:
                    raise AiConflict("Review inputs changed.")
                context.validate_sources(message.sources)
            except SQLAlchemyError:
                raise
            except Exception:
                result.update(content=None, sources=(), stale=True)
        return row, result

    def get(self, user_id: UUID, identifier: UUID):
        with self.transactions(user_id) as context:
            return self.read(context, user_id, identifier)[1]

    def discuss(self, user_id: UUID, identifier: UUID):
        with self.transactions(user_id) as context:
            row, report = self.read(context, user_id, identifier)
            if row.status != "completed" or report["stale"]:
                raise AiConflict("A current completed review is required.")
            row.discussed = True
            return {"conversation_id": row.conversation_id}
