import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from test_logging import capture_json

from app.core.config import Settings
from app.modules.ai.domain.state import AiPersistenceUnavailable
from app.modules.search.application.embeddings import EmbeddingProfile


def test_worker_errors_do_not_log_private_source_or_sql_parameters():
    initial = Settings.model_construct(
        database_url="postgresql+psycopg://test:test@localhost/test",
        redis_url="redis://localhost:6379/15",
        s3_endpoint="http://localhost:8333",
        s3_access_key="synthetic",
        s3_secret_key="synthetic-only",
        s3_bucket="test",
    )
    with patch("app.core.config.get_settings", return_value=initial):
        document_tasks = importlib.import_module("app.modules.ai.infrastructure.document_tasks")
        index_tasks = importlib.import_module("app.modules.search.infrastructure.tasks")
    private = "private document body or SQL parameter"
    engine = Mock()
    provider = SimpleNamespace(
        profile=EmbeddingProfile("fake", "model", "v1", 384, 512, True), count_tokens=len
    )
    settings = SimpleNamespace(search_embeddings_directory=Path("/not-used"))
    with (
        patch.object(index_tasks, "get_settings", return_value=settings),
        patch.object(index_tasks, "create_database_engine", return_value=engine),
        patch.object(index_tasks, "embedding_provider", return_value=provider),
        patch.object(index_tasks.IndexingService, "process", side_effect=RuntimeError(private)),
        capture_json() as logs,
    ):
        with pytest.raises(index_tasks.IndexUnavailable) as error:
            index_tasks.process(
                "11111111-1111-4111-8111-111111111111",
                "page",
                "22222222-2222-4222-8222-222222222222",
            )
        assert private not in str(error.value) and private not in str(logs)
    processor = Mock()
    processor.process.side_effect = RuntimeError(private)
    with (
        patch.object(document_tasks, "get_settings", return_value=SimpleNamespace(ai_enabled=True)),
        patch.object(document_tasks, "create_database_engine", return_value=engine),
        patch.object(document_tasks, "document_service", return_value=(None, processor)),
        capture_json() as logs,
    ):
        with pytest.raises(AiPersistenceUnavailable) as error:
            document_tasks.process("11111111-1111-4111-8111-111111111111")
        assert private not in str(error.value) and private not in str(logs)
