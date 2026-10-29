import logging
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.integrations.bsuir.academics import IisAcademicProvider
from app.modules.ai.application.connections import ConnectionAccess
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.infrastructure.connections import FileConnectionConfiguration
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.providers import OpenRouterModels
from app.modules.ai.infrastructure.review_generation import ReviewAgentModel
from app.modules.ai.infrastructure.review_jobs import ReviewJobs
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def review_jobs(sessions, settings, academics):
    transactions = SqlAlchemyAiTransactions(sessions)
    access = (
        ConnectionAccess(FileConnectionConfiguration(settings.ai_connections_file))
        if settings.ai_connections_file
        else None
    )
    service = AiService(transactions, PostgresAgentRunners(sessions), connections=access)
    models = OpenRouterModels(transactions, access) if access else None
    reader = SqlAlchemySourceReader(sessions, academics, settings.schedule_sync_interval_seconds)
    return ReviewJobs(
        service,
        reader,
        ReviewAgentModel(service, models),
        enabled=lambda: get_settings().ai_enabled and get_settings().ai_reviews_enabled,
    )


def execute(identifier: str | None = None):
    settings = get_settings()
    if not settings.ai_enabled or not settings.ai_reviews_enabled:
        return
    engine = create_database_engine(settings)
    try:
        # Review collection reads stored academic facts; accidental remote discovery fails closed.
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    RuntimeError("Reviews use stored sources only.")
                )
            )
        ) as client:
            jobs = review_jobs(
                create_session_factory(engine), settings, IisAcademicProvider(client)
            )
            if identifier is not None:
                jobs.process(UUID(identifier))
            else:
                jobs.recover()
                for review_id in jobs.scan():
                    celery_app.send_task(
                        "ai.reviews.process",
                        kwargs={"review_id": str(review_id)},
                        queue="ai-documents",
                    )
    except Exception as error:
        log_failure(logger, "ai.review_failed", error)
    finally:
        engine.dispose()


@celery_app.task(name="ai.reviews.dispatch", ignore_result=True, store_errors_even_if_ignored=False)
def dispatch():
    execute()


@celery_app.task(
    name="ai.reviews.process",
    ignore_result=True,
    store_errors_even_if_ignored=False,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process(review_id: str):
    execute(review_id)
