import logging
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.integrations.storage.materials import S3MaterialStorage
from app.modules.materials.infrastructure.extractor import BoundedDocumentExtractor
from app.modules.materials.infrastructure.jobs import (
    MaterialJobUnavailable,
    dispatch_materials,
    process_material,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_job(material_id: str | None = None) -> None:
    try:
        identifier = UUID(material_id) if material_id is not None else None
        settings = get_settings()
        engine = create_database_engine(settings)
        try:
            storage = S3MaterialStorage(settings)
            try:
                sessions = create_session_factory(engine)
                if identifier is None:
                    dispatch_materials(
                        sessions,
                        storage,
                        celery_app,
                        reextract_legacy=settings.ai_enabled
                        or settings.search_embeddings_directory is not None,
                    )
                else:
                    process_material(sessions, storage, BoundedDocumentExtractor(), identifier)
            finally:
                storage.close()
        finally:
            engine.dispose()
    except Exception as error:
        log_failure(logger, "materials.task_failed", error)
        raise MaterialJobUnavailable("Material processing is unavailable.") from None


@celery_app.task(
    name="materials.dispatch",
    ignore_result=True,
    store_errors_even_if_ignored=False,
    autoretry_for=(MaterialJobUnavailable,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def dispatch() -> None:
    run_job()


@celery_app.task(
    name="materials.process",
    ignore_result=True,
    store_errors_even_if_ignored=False,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process(material_id: str) -> None:
    if not isinstance(material_id, str):
        raise MaterialJobUnavailable("Invalid material job.")
    run_job(material_id)
