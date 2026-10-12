import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import create_event
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_logging import capture_json, entries
from test_notes_http import BASE, change, create_page, lifecycle
from test_relations_http import backlinks, event_path

from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import PageConflict
from app.modules.notes.infrastructure.orm import PageModel
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def document(*blocks: dict) -> dict:
    return {"schema_version": 1, "blocks": list(blocks)}


def block(kind: str = "text", **values) -> dict:
    return {"id": str(uuid4()), "type": kind} | values


def save_document(client: TestClient, page: dict, body: dict, **values):
    return client.put(
        f"{BASE}/{page['id']}/document",
        headers=csrf_headers(client),
        json={"expected_version": page["version"], "document": body} | values,
    )


def test_document_edit_remove_reorder_and_legacy_safety(calendar_client: TestClient) -> None:
    original = "# Notes\r\n\n**keep** <raw> Привет 😀"
    page = create_page(calendar_client, content=original)
    path = f"{BASE}/{page['id']}/document"
    legacy = document(block(id=page["id"], text=original, text_format="markdown"))
    assert page["document"] == legacy
    assert calendar_client.get(path).json() == {
        "page_id": page["id"],
        "version": 1,
        "document": legacy,
    }
    page = change(calendar_client, page, content=original + "\nMore").json()
    assert page["document"]["blocks"][0]["id"] == page["id"]
    body = document(
        block("heading", text="Chest", level=2),
        block(text="Press", text_format="plain"),
        block("list", items=["Warm up", "Work sets"], style="numbered"),
        block("checkbox", text="Done", checked=False),
        block("link", text="Plan", url="https://example.com/plan"),
    )
    saved = save_document(calendar_client, page, body)
    assert saved.status_code == 200 and saved.json()["version"] == 3
    assert saved.json()["document"] == body
    assert save_document(calendar_client, page, document()).status_code == 409
    page = calendar_client.get(f"{BASE}/{page['id']}").json()
    assert page["content"] == (
        "## Chest\n\nPress\n\n1. Warm up\n2. Work sets\n\n- [ ] Done\n\n"
        "[Plan](<https://example.com/plan>)"
    )
    assert change(calendar_client, page, content="flatten").status_code == 409
    assert change(calendar_client, page, document=body).status_code == 422
    page = change(calendar_client, page, title="Updated title").json()
    assert page["document"] == body
    edited = document(body["blocks"][3] | {"checked": True}, body["blocks"][0])
    assert save_document(calendar_client, page, edited).json()["document"] == edited
    stored = calendar_client.get(path)
    assert stored.json()["version"] == 5 and stored.json()["document"] == edited
    assert stored.headers["cache-control"] == "no-store"


def test_empty_document_keeps_legacy_content_writes(calendar_client: TestClient) -> None:
    page = create_page(calendar_client, document=document())
    assert page["document"] == document() and page["content"] == ""
    page = change(calendar_client, page, content="Legacy").json()
    assert page["document"]["blocks"][0]["id"] == page["id"]
    assert change(calendar_client, page, content="").json()["document"] == document()


@pytest.mark.parametrize(
    "body",
    [
        {"blocks": []},
        {"schema_version": True, "blocks": []},
        document(block("heading", text="T", level=True)),
        document(block("checkbox", text="T", checked="false")),
        document(block(text="T", unknown="x")),
        document(block("link", text="T", url="javascript:alert(1)")),
        document(block(text="a" * 60000), block(text="b" * 60000)),
        document(block(id=str(UUID(int=1)), text="A"), block(id=str(UUID(int=1)), text="B")),
    ],
)
def test_invalid_documents_do_not_change_page(calendar_client: TestClient, body: dict) -> None:
    page = create_page(calendar_client)
    assert save_document(calendar_client, page, body).status_code == 422
    assert calendar_client.get(f"{BASE}/{page['id']}").json() == page
    assert (
        calendar_client.post(
            BASE, headers=csrf_headers(calendar_client), json={"title": "T", "document": body}
        ).status_code
        == 422
    )


def test_creation_rejects_ambiguous_content_and_null(calendar_client: TestClient) -> None:
    for values in ({"document": None}, {"document": document(), "content": ""}):
        assert (
            calendar_client.post(
                BASE, headers=csrf_headers(calendar_client), json={"title": "T"} | values
            ).status_code
            == 422
        )
    assert calendar_client.get(BASE).json()["items"] == []


def test_invalid_unicode_json_is_rejected(calendar_client: TestClient) -> None:
    page = create_page(calendar_client)
    body = document(block(text="\ud800"))
    for method, path, values in (
        ("PUT", f"{BASE}/{page['id']}/document", {"expected_version": 1}),
        ("POST", BASE, {"title": "T"}),
    ):
        response = calendar_client.request(
            method,
            path,
            headers=csrf_headers(calendar_client) | {"Content-Type": "application/json"},
            content=json.dumps(values | {"document": body}),
        )
        assert response.status_code == 422
    assert calendar_client.get(f"{BASE}/{page['id']}").json() == page


def test_document_ownership_csrf_and_trash(
    calendar_client: TestClient, concurrent_engine: Engine, password_hash: str
) -> None:
    body = document(block("checkbox", text="Done", checked=True))
    page = create_page(calendar_client, document=body)
    path = f"{BASE}/{page['id']}/document"
    assert (
        calendar_client.put(path, json={"expected_version": 1, "document": body}).status_code == 403
    )
    assert save_document(calendar_client, page, body, expected_version=True).status_code == 422
    trashed = lifecycle(calendar_client, page, "trash").json()
    assert calendar_client.get(path).json()["document"] == body
    assert save_document(calendar_client, trashed, document()).status_code == 409
    restored = lifecycle(calendar_client, trashed, "restore").json()
    assert restored["document"] == body and restored["version"] == 3
    seed_user(concurrent_engine, "other@example.com", password_hash)
    browser_login(calendar_client, "other@example.com")
    assert calendar_client.get(path).status_code == 404
    assert save_document(calendar_client, restored, body).status_code == 404
    calendar_client.cookies.clear()
    assert calendar_client.get(path).status_code == 401
    assert save_document(calendar_client, restored, body).status_code == 401


def test_documents_created_from_events_and_summary_queries(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    parent, calendar_event = create_page(calendar_client), create_event(calendar_client)
    path = event_path("personal", calendar_event["id"])
    body = document(block("heading", text="Plan", level=1))
    response = calendar_client.post(
        path,
        headers=csrf_headers(calendar_client),
        json={"title": "Chest", "parent_id": parent["id"], "document": body},
    )
    assert response.status_code == 201
    page = calendar_client.get(f"{BASE}/{response.json()['page']['id']}").json()
    assert page["document"] == body and page["parent_id"] == parent["id"]
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(concurrent_engine, "before_cursor_execute", capture)
    try:
        assert len(calendar_client.get(BASE).json()["items"]) == 2
        assert len(calendar_client.get(path).json()["items"]) == 1
        assert len(backlinks(calendar_client, page)["items"]) == 1
    finally:
        event.remove(concurrent_engine, "before_cursor_execute", capture)
    assert any("note_pages" in sql for sql in statements)
    assert all("note_pages.document" not in sql for sql in statements)
    assert save_document(calendar_client, page, document()).status_code == 200
    assert len(backlinks(calendar_client, page)["items"]) == 1


def test_document_storage_failure_rolls_back_without_success_log(
    calendar_client: TestClient,
) -> None:
    page = create_page(calendar_client, content="Original")
    original = SqlAlchemyPageRepository.save

    def fail(self, value, expected_version):
        original(self, value, expected_version)
        raise SQLAlchemyError("private-document-sql")

    with patch.object(SqlAlchemyPageRepository, "save", fail), capture_json() as output:
        response = save_document(calendar_client, page, document(block(text="private-body")))
    assert response.status_code == 503 and "private" not in response.text
    assert (
        "private-document-sql" not in output.getvalue() and "private-body" not in output.getvalue()
    )
    assert not any(row["event"] == "notes.document_updated" for row in entries(output))
    assert calendar_client.get(f"{BASE}/{page['id']}").json() == page


def test_document_and_metadata_share_one_concurrent_version(
    calendar_client: TestClient, concurrent_engine: Engine
) -> None:
    page = create_page(calendar_client, content="Original")
    with Session(concurrent_engine) as database:
        row = database.get(PageModel, UUID(page["id"]))
        assert row is not None
        owner = row.user_id
    body = document(block("heading", text="Edited", level=1))

    def update(document_write: bool) -> bool:
        try:
            with Session(concurrent_engine) as database, database.begin():
                notes = NoteService(
                    SqlAlchemyPageRepository(database), SqlAlchemyUserAuthentication(database)
                )
                if document_write:
                    notes.replace_document(owner, UUID(page["id"]), body, 1)
                else:
                    notes.update(owner, UUID(page["id"]), {"title": "Renamed"}, 1)
            return True
        except PageConflict:
            return False

    with ThreadPoolExecutor(2) as pool:
        writes = [pool.submit(update, True), pool.submit(update, False)]
        results = [future.result() for future in writes]
    assert sorted(results) == [False, True]
    stored = calendar_client.get(f"{BASE}/{page['id']}").json()
    assert stored["version"] == 2
    assert stored["document"] == (body if results[0] else page["document"])
    assert stored["title"] == (page["title"] if results[0] else "Renamed")
