from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import Engine, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_ai_persistence import ai_database as ai_database
from test_ai_persistence import make_message, migration_config, seed

from alembic import command
from app.modules.academics.application.ports import AcademicProvider
from app.modules.ai.application.source_queries import (
    CalendarRead,
    DatabaseList,
    DatabaseRead,
    DatabaseReadQuery,
    MaterialRead,
    PageRead,
    PropertyFilter,
    SearchRead,
)
from app.modules.ai.infrastructure.orm import MessageModel
from app.modules.ai.infrastructure.repository import SqlAlchemyAiRepository
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.materials.application.service import MaterialService
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.search.domain.evidence import SourceReference
from app.modules.search.infrastructure.documents import SqlAlchemyMaterialTextIndex


def source_reader(engine: Engine) -> SqlAlchemySourceReader:
    return SqlAlchemySourceReader(sessionmaker(engine), Mock(spec=AcademicProvider), 3600)


def test_source_metadata_round_trip_constraints_and_preserving_migration(ai_database: Engine):
    conversation, _ = seed(ai_database)
    citation = SourceReference(source="page", id=str(uuid4()), version=3, title="Read source")
    message = replace(make_message(conversation), role="assistant", sources=(citation,))
    with Session(ai_database) as session, session.begin():
        repository = SqlAlchemyAiRepository(session)
        repository.append_message(message)
        assert repository.messages(conversation.user_id, conversation.id, 0, 20) == [message]
        assert repository.messages(uuid4(), conversation.id, 0, 20) == []
    with ai_database.begin() as connection:
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(update(MessageModel).values(sources={"invalid": True}))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(update(MessageModel).values(role="user"))
        with pytest.raises(DBAPIError, match="Cannot downgrade"), connection.begin_nested():
            command.downgrade(migration_config(connection), "0024_ai_connections")
        connection.execute(update(MessageModel).values(sources=[]))
        command.downgrade(migration_config(connection), "0024_ai_connections")
        command.upgrade(migration_config(connection), "head")
        command.check(migration_config(connection))
    with Session(ai_database) as session:
        assert (
            SqlAlchemyAiRepository(session)
            .messages(conversation.user_id, conversation.id, 0, 20)[0]
            .content
            == message.content
        )


def test_source_reads_use_current_owner_versions_filters_and_character_ranges(ai_database: Engine):
    conversation, other = seed(ai_database)
    owner = conversation.user_id
    reader = source_reader(ai_database)
    with Session(ai_database) as session, session.begin():
        service = reader.service(session)
        page = service.notes.create(owner, "Normalization", "Первая строка 🙂\nSecond line")
        foreign = service.notes.create(other, "Foreign secret", "Normalization secret")
        database = service.views.databases.create(owner, "Reading")
        prop = service.views.content.create_property(owner, database.id, 1, "Score", "number")
        record = service.views.content.create_record(
            owner, database.id, prop.schema_version, {str(prop.property.id): 7}, page_id=page.id
        )
        material_service = MaterialService(
            service.materials.materials, service.materials.users, Mock()
        )
        material = material_service.create_upload(owner, "lecture.txt", 10)
        session.execute(
            update(MaterialModel).where(MaterialModel.id == material.id).values(status="ready")
        )
        SqlAlchemyMaterialTextIndex(session).put(owner, material.id, "Текст🙂 файла")
    assert reader.read(other, PageRead(page_id=page.id)).status == "not_found"
    assert reader.read(owner, PageRead(page_id=foreign.id)).status == "not_found"
    excerpt = reader.read(owner, PageRead(page_id=page.id, offset=1, limit=3))
    assert excerpt.coverage == "partial" and excerpt.next_offset == 4
    assert excerpt.sources[0].version == page.version
    material_result = reader.read(owner, MaterialRead(material_id=material.id, offset=5, limit=2))
    assert material_result.data == {"text": "🙂 ", "total_characters": 12}
    assert material_result.coverage == "partial"
    hits = reader.read(owner, SearchRead(query="Normalization", source_ids=(page.id,)))
    assert [item.id for item in hits.sources] == [str(page.id)]
    assert (
        reader.read(owner, SearchRead(query="Normalization", source_ids=(foreign.id,))).sources
        == ()
    )
    assert reader.read(owner, DatabaseList()).sources[0].id == str(database.id)
    assert reader.read(owner, DatabaseRead(database_id=database.id)).status == "ok"
    filtered = reader.read(
        owner,
        DatabaseReadQuery(
            database_id=database.id,
            filters=(PropertyFilter(property_id=prop.property.id, operator="gte", value=6),),
        ),
    )
    assert filtered.sources[0].id == str(record.record.id)
    assert filtered.coverage == "complete"
    assert reader.read(other, DatabaseRead(database_id=database.id)).status == "not_found"
    assert (
        reader.read(
            owner,
            DatabaseReadQuery(
                database_id=database.id,
                filters=(PropertyFilter(property_id=uuid4(), operator="eq", value=1),),
            ),
        ).status
        == "invalid"
    )
    with Session(ai_database) as session, session.begin():
        service = reader.service(session)
        updated = service.notes.update(owner, page.id, {"content": "Changed"}, page.version)
        service.materials.materials.save(
            replace(material, status="ready", trashed_at=datetime.now(UTC), version=2),
            1,
        )
    current = reader.read(owner, PageRead(page_id=page.id))
    assert current.sources[0].version == updated.version
    assert reader.read(owner, MaterialRead(material_id=material.id)).status == "not_found"
    with Session(ai_database) as session, session.begin():
        reader.service(session).notes.trash(owner, page.id, updated.version)
    assert reader.read(owner, PageRead(page_id=page.id)).status == "not_found"
    assert not reader.read(owner, DatabaseReadQuery(database_id=database.id)).sources


def test_calendar_combines_record_dates_and_events_without_claiming_availability(
    ai_database: Engine,
):
    conversation, _ = seed(ai_database)
    owner, reader = conversation.user_id, source_reader(ai_database)
    now = datetime.now(UTC) + timedelta(hours=2)
    with Session(ai_database) as session, session.begin():
        service = reader.service(session)
        service.calendar.calendar.create_personal_event(
            owner,
            {
                "title": "Appointment",
                "starts_at": now,
                "ends_at": now + timedelta(hours=1),
                "description": "🙂" * 5000,
            },
        )
        database = service.views.databases.create(owner, "Dates")
        prop = service.views.content.create_property(owner, database.id, 1, "Deadline", "date")
        service.views.content.create_record(
            owner,
            database.id,
            prop.schema_version,
            {str(prop.property.id): {"kind": "date", "start": now.date().isoformat(), "end": None}},
            title="Read book",
        )
        service.views.create(
            owner,
            database.id,
            prop.schema_version,
            "Calendar",
            layout="calendar",
            date_property_id=prop.property.id,
        )
    result = reader.read(owner, CalendarRead(date_from=now.date(), date_to=now.date()))
    assert result.status == "ok", result
    assert {source.source for source in result.sources} == {"personal", "record_date"}
    assert "calendar_display_is_not_availability" in result.warnings
    assert "academic_profile_not_selected" in result.warnings
    assert "event_summaries_descriptions_omitted" in result.warnings
    assert (
        reader.read(
            owner,
            CalendarRead(date_from=now.date(), date_to=now.date(), database_view_ids=(uuid4(),)),
        ).status
        == "not_found"
    )


def test_large_database_option_lists_are_readable_through_schema_pagination(ai_database: Engine):
    conversation, _ = seed(ai_database)
    owner, reader = conversation.user_id, source_reader(ai_database)
    options = [{"id": str(uuid4()), "name": "🙂" * 100} for _ in range(40)]
    # Option names are unique under the normal schema contract.
    for index, option in enumerate(options):
        option["name"] = str(index) + "🙂" * 98
    with Session(ai_database) as session, session.begin():
        service = reader.service(session)
        database = service.views.databases.create(owner, "Large schema")
        prop = service.views.content.create_property(
            owner, database.id, 1, "Choice", "select", options
        )
    schema = reader.read(owner, DatabaseRead(database_id=database.id))
    assert schema.status == "ok" and schema.coverage == "complete"
    page = reader.read(owner, DatabaseRead(database_id=database.id, property_id=prop.property.id))
    assert page.status == "ok" and page.next_offset == 5 and page.coverage == "partial"
    assert isinstance(page.data, dict)
    assert isinstance(page.data["options"], list) and len(page.data["options"]) == 5
