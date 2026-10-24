from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import Engine, update
from sqlalchemy.orm import Session, sessionmaker
from test_ai_persistence import ai_database as ai_database
from test_ai_persistence import seed

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
from app.modules.ai.infrastructure.sources import SqlAlchemySourceReader
from app.modules.materials.application.service import MaterialService
from app.modules.materials.infrastructure.orm import MaterialModel
from app.modules.search.infrastructure.documents import SqlAlchemyMaterialTextIndex


def source_reader(engine: Engine) -> SqlAlchemySourceReader:
    return SqlAlchemySourceReader(sessionmaker(engine), Mock(spec=AcademicProvider), 3600)


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
    assert (
        reader.read(
            owner,
            CalendarRead(date_from=now.date(), date_to=now.date(), database_view_ids=(uuid4(),)),
        ).status
        == "not_found"
    )
