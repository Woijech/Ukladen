import logging
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.documents import DocumentAnalysisService
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.domain.state import AiPersistenceUnavailable
from app.modules.ai.infrastructure.connections import FileConnectionConfiguration
from app.modules.ai.infrastructure.document_jobs import SqlAlchemyDocumentSteps
from app.modules.ai.infrastructure.document_runtime import DocumentAgentModel
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.providers import OpenRouterModels
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def document_service(sessions, settings):
    transactions = SqlAlchemyAiTransactions(sessions)
    access = (
        ConnectionAccess(FileConnectionConfiguration(settings.ai_connections_file))
        if settings.ai_connections_file
        else None
    )
    service = AiService(transactions, PostgresAgentRunners(sessions), connections=access)
    steps = SqlAlchemyDocumentSteps(sessions, service)
    models = OpenRouterModels(transactions, access, background=True) if access else None
    return steps, DocumentAnalysisService(steps, DocumentAgentModel(steps, models))


@celery_app.task(
    name="ai.documents.dispatch", ignore_result=True, store_errors_even_if_ignored=False
)
def dispatch() -> None:
    settings = get_settings()
    if not settings.ai_enabled:
        return
    engine = create_database_engine(settings)
    try:
        steps, _ = document_service(create_session_factory(engine), settings)
        for run_id in steps.candidates():
            celery_app.send_task(
                "ai.documents.process", kwargs={"run_id": str(run_id)}, queue="ai-documents"
            )
    finally:
        engine.dispose()


@celery_app.task(
    name="ai.documents.process",
    ignore_result=True,
    store_errors_even_if_ignored=False,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process(run_id: str) -> None:
    settings = get_settings()
    if not settings.ai_enabled:
        return
    engine = create_database_engine(settings)
    try:
        _, processor = document_service(create_session_factory(engine), settings)
        if processor.process(UUID(run_id)):
            celery_app.send_task(
                "ai.documents.process", kwargs={"run_id": run_id}, queue="ai-documents"
            )
    except Exception as error:
        log_failure(logger, "ai.document_step_failed", error)
        raise AiPersistenceUnavailable("Document processing is unavailable.") from None
    finally:
        engine.dispose()
