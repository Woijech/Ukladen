import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, select
from sqlalchemy.orm import sessionmaker
from test_auth_persistence import database_connection as database_connection
from test_auth_persistence import migration_config
from test_auth_sessions import concurrent_engine as concurrent_engine

from alembic import command
from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.documents import DocumentAnalysisService
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.application.source_queries import SourceScope
from app.modules.ai.domain.state import AiNotFound
from app.modules.ai.infrastructure.document_jobs import SqlAlchemyDocumentSteps
from app.modules.ai.infrastructure.document_models import DocumentJobModel
from app.modules.ai.infrastructure.document_runtime import DocumentAgentModel
from app.modules.ai.infrastructure.lifecycle import PostgresAgentRunners, SqlAlchemyAiTransactions
from app.modules.ai.infrastructure.orm import ProviderAttemptModel
from app.modules.ai.infrastructure.recovery import reconcile_runs
from app.modules.notes.domain.blocks import document_value, markdown_document
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.users.infrastructure.orm import UserModel


def setup(engine, text="lecture requirements " * 300):
    sessions = sessionmaker(engine, expire_on_commit=False)
    user, page = uuid4(), uuid4()
    with sessions.begin() as database:
        database.add(UserModel(id=user, email=f"{user}@example.com"))
        database.flush()
        database.add(
            PageModel(
                id=page,
                user_id=user,
                title="Lecture notes",
                document=document_value(markdown_document(text)),
            )
        )
    service = AiService(SqlAlchemyAiTransactions(sessions), PostgresAgentRunners(sessions))
    conversation = service.create(user, "Full-source comparison")
    request = AgentInput(
        conversation_id=conversation.id,
        message="Find all requirements in these notes.",
        source_scope=SourceScope(page_ids=(page,)),
        full_sources=True,
    )
    run, _ = service.admit(user, request, uuid4())
    return sessions, service, user, page, run, request


class Model:
    def __init__(self):
        self.fragments = []

    def generate(self, step):
        data = json.loads(step.evidence)
        if step.phase == "reading":
            self.fragments.append((data["start"], data["end"], data["text"]))
        return "Evidence summary with source attribution."


def test_complete_source_processing_reads_every_range_and_resumes(concurrent_engine):
    body = "требования к лабораторной. " * 150
    sessions, service, owner, page, run, request = setup(concurrent_engine, body)
    model = Model()
    processor = DocumentAnalysisService(SqlAlchemyDocumentSteps(sessions, service), model)
    assert processor.process(run.id)
    # A new processor instance continues the persisted cursor, not the first fragment.
    for _ in range(100):
        processor = DocumentAnalysisService(SqlAlchemyDocumentSteps(sessions, service), model)
        if not processor.process(run.id):
            break
    else:
        pytest.fail("Source processing did not converge.")
    assert "".join(item[2] for item in model.fragments) == body
    assert service.get_run(owner, run.id).run.status == "completed"
    progress = SqlAlchemyDocumentSteps(sessions, service).progress(owner, run.id)
    assert progress is not None
    assert progress["processed_characters"] == progress["total_characters"] == len(body)
    assert progress["phase"] == "completed"
    messages = service.history(owner, request.conversation_id, 0, 100)
    assert len(messages) == 2 and messages[-1].sources[0].version == 1
    assert not processor.process(run.id)
    other = uuid4()
    with sessions.begin() as database:
        database.add(UserModel(id=other, email="other-documents@example.com"))
    with pytest.raises(AiNotFound):
        SqlAlchemyDocumentSteps(sessions, service).progress(other, run.id)


def test_source_edit_and_cancel_fence_inflight_analysis(concurrent_engine):
    sessions, service, owner, page, run, _ = setup(concurrent_engine)
    steps = SqlAlchemyDocumentSteps(sessions, service)
    work = steps.claim(run.id)
    assert work
    with sessions.begin() as database:
        current = database.get(PageModel, page)
        assert current
        current.version += 1
        current.document = document_value(markdown_document("updated"))
    assert not steps.complete(work, "obsolete source summary")
    assert service.get_run(owner, run.id).run.status == "failed"
    progress = steps.progress(owner, run.id)
    assert progress is not None and progress["error"] == "source_changed_or_unavailable"
    sessions, service, owner, page, run, _ = setup(concurrent_engine)
    steps = SqlAlchemyDocumentSteps(sessions, service)
    work = steps.claim(run.id)
    assert work
    service.cancel(owner, run.id)
    assert not steps.complete(work, "late result")
    assert service.get_run(owner, run.id).run.status == "cancelled"


def test_framework_steps_keep_usage_past_four_calls_and_chat_deletion_cascades(concurrent_engine):
    sessions, service, owner, page, run, request = setup(concurrent_engine, "source " * 1800)
    steps = SqlAlchemyDocumentSteps(sessions, service)
    processor = DocumentAnalysisService(steps, DocumentAgentModel(steps))
    for _ in range(100):
        if not processor.process(run.id):
            break
    snapshot = service.get_run(owner, run.id)
    assert snapshot.run.status == "completed"
    assert len(snapshot.attempts) > 4
    assert all(item.status == "succeeded" for item in snapshot.attempts)
    service.delete(owner, request.conversation_id)
    with sessions() as database:
        assert database.get(DocumentJobModel, run.id) is None
        assert (
            database.scalar(
                select(ProviderAttemptModel.id).where(ProviderAttemptModel.run_id == run.id)
            )
            is not None
        )


def test_background_recovery_uses_lease_and_never_foreground_deadline(concurrent_engine):
    sessions, service, owner, page, run, _ = setup(concurrent_engine)
    now = datetime.now(UTC)
    steps = SqlAlchemyDocumentSteps(sessions, service, now=lambda: now)
    first = steps.claim(run.id)
    assert first and steps.claim(run.id) is None
    assert reconcile_runs(sessions, now=now + timedelta(minutes=1)) == 0
    now += timedelta(minutes=3)
    second = steps.claim(run.id)
    assert second and second.lease != first.lease
    assert not steps.complete(first, "obsolete")
    assert steps.complete(second, "current")


def test_full_source_selection_is_explicit_and_not_a_document_quota():
    selected = SourceScope(page_ids=tuple(uuid4() for _ in range(100)))
    assert len(selected.page_ids) == 100


def test_document_job_migration_matches_metadata(database_connection: Connection):
    command.check(migration_config(database_connection))
    command.downgrade(migration_config(database_connection), "0029_search_chunks")
    command.upgrade(migration_config(database_connection), "head")
    command.check(migration_config(database_connection))


def test_prior_analysis_context_rechecks_versions_and_explicit_scope(concurrent_engine):
    from app.modules.ai.infrastructure.document_context import AnalysisContext

    sessions, service, owner, page, run, request = setup(concurrent_engine, "Lecture facts")
    processor = DocumentAnalysisService(SqlAlchemyDocumentSteps(sessions, service), Model())
    for _ in range(10):
        if not processor.process(run.id):
            break
    context = AnalysisContext(sessions)
    assert context.read(owner, request.conversation_id, None).sources
    assert not context.read(owner, request.conversation_id, SourceScope()).sources
    with sessions.begin() as database:
        row = database.get(PageModel, page)
        assert row
        row.version += 1
    assert context.read(owner, request.conversation_id, None).warnings == (
        "prior_analysis_sources_changed",
    )


def test_disabled_owner_stops_background_work_without_model_dispatch(concurrent_engine):
    sessions, service, owner, _, run, _ = setup(concurrent_engine)
    with sessions.begin() as database:
        row = database.get(UserModel, owner)
        assert row
        row.status = "disabled"
    model = Model()
    steps = SqlAlchemyDocumentSteps(sessions, service)
    assert not DocumentAnalysisService(steps, model).process(run.id)
    assert model.fragments == []
    with sessions() as database:
        job = database.get(DocumentJobModel, run.id)
        assert job and job.phase == "failed" and job.error == "owner_unavailable"


def test_worker_recovery_closes_unknown_attempt_and_fences_late_completion(concurrent_engine):
    from app.modules.ai.application.lifecycle import RunJournal

    sessions, service, owner, _, run, request = setup(concurrent_engine, "Synthetic facts. " * 200)
    now = datetime.now(UTC)
    steps = SqlAlchemyDocumentSteps(sessions, service, now=lambda: now)
    interrupted = steps.claim(run.id)
    assert interrupted
    current = service.get_run(owner, run.id).run
    attempt = RunJournal(service, current, background=True).start_attempt()
    assert run.id not in steps.candidates()
    now += timedelta(minutes=3)
    assert run.id in SqlAlchemyDocumentSteps(sessions, service, now=lambda: now).candidates()
    replacement = steps.claim(run.id)
    assert replacement and replacement.lease != interrupted.lease
    assert replacement.next_offset == interrupted.next_offset
    snapshot = service.get_run(owner, run.id)
    closed = next(item for item in snapshot.attempts if item.id == attempt.id)
    assert closed.status == "interrupted"
    assert closed.input_tokens is None and closed.output_tokens is None
    assert not steps.complete(interrupted, "Late duplicate result")
    assert steps.complete(replacement, "Current source summary")
    for _ in range(100):
        fresh_steps = SqlAlchemyDocumentSteps(sessions, service, now=lambda: now)
        if not DocumentAnalysisService(fresh_steps, DocumentAgentModel(fresh_steps)).process(
            run.id
        ):
            break
    else:
        pytest.fail("Recovered document processing did not converge.")
    final = service.get_run(owner, run.id)
    assert final.run.status == "completed"
    progress = steps.progress(owner, run.id)
    assert progress and progress["processed_characters"] == progress["total_characters"]
    assert len(service.history(owner, request.conversation_id, 0, 100)) == 2
    assert len(final.attempts) > 1
    assert not DocumentAnalysisService(steps, DocumentAgentModel(steps)).process(run.id)
