from uuid import UUID

from sqlalchemy import select, text

from app.modules.ai.application.source_queries import SourceScope
from app.modules.ai.infrastructure.document_models import DocumentJobModel
from app.modules.ai.infrastructure.orm import MessageModel
from app.modules.search.application.evidence import EvidenceResult
from app.modules.search.domain.evidence import SourceReference
from app.modules.search.infrastructure.source_documents import SqlAlchemySourceDocuments
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


class AnalysisContext:
    """Rebuild prior analysis from current authorized sources at every model dispatch."""

    def __init__(self, sessions):
        self.sessions = sessions

    def read(
        self, user_id: UUID, conversation_id: UUID | None, scope: SourceScope | None
    ) -> EvidenceResult:
        with self.sessions.begin() as database:
            database.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            database.execute(text("SET LOCAL statement_timeout = '5s'"))
            if not SqlAlchemyUserAuthentication(database).is_active(user_id):
                return EvidenceResult(status="not_found")
            row = database.execute(
                select(DocumentJobModel, MessageModel)
                .join(
                    MessageModel,
                    (MessageModel.id == DocumentJobModel.answer_message_id)
                    & (MessageModel.user_id == DocumentJobModel.user_id),
                )
                .where(
                    DocumentJobModel.user_id == user_id,
                    DocumentJobModel.conversation_id == conversation_id,
                    DocumentJobModel.phase == "completed",
                )
                .order_by(MessageModel.sequence.desc())
                .limit(1)
            ).one_or_none()
            if row is None:
                return EvidenceResult()
            job, answer = row
            documents = SqlAlchemySourceDocuments(database)
            for item in job.manifest:
                allowed = (
                    scope.page_ids
                    if scope and item["source"] == "page"
                    else scope.material_ids
                    if scope
                    else ()
                )
                if scope is not None and UUID(item["id"]) not in allowed:
                    return EvidenceResult(warnings=("prior_analysis_outside_current_scope",))
                identity = documents.identity(user_id, item["source"], UUID(item["id"]))
                if identity is None or identity[0] != item["version"]:
                    return EvidenceResult(warnings=("prior_analysis_sources_changed",))
            return EvidenceResult(
                data={
                    "question": job.question.encode()[:800].decode("utf-8", errors="ignore"),
                    "answer": answer.content.encode()[:4000].decode("utf-8", errors="ignore"),
                },
                sources=tuple(
                    SourceReference(
                        source=item["source"],
                        id=item["id"],
                        title=item["title"],
                        version=item["version"],
                        locator="full-extracted-text",
                    )
                    for item in job.manifest[:8]
                ),
                coverage="partial",
                warnings=("prior_analysis_preview_not_full_sources",),
            )
