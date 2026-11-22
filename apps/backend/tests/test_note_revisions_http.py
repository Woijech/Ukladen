from fastapi.testclient import TestClient
from test_auth_http import csrf_headers
from test_calendar_http import browser_settings as browser_settings
from test_calendar_http import calendar_client as calendar_client
from test_calendar_http import concurrent_engine as concurrent_engine
from test_calendar_http import live_client as live_client
from test_calendar_http import password_hash as password_hash
from test_calendar_http import settings as settings
from test_note_documents_http import block, document, save_document
from test_notes_http import BASE, create_page


def test_revision_restore_is_explicit_versioned_and_preserves_current_history(
    calendar_client: TestClient,
):
    page = create_page(calendar_client, title="Original", content="Preserve this")
    path = f"{BASE}/{page['id']}"
    original = page["document"]
    saved = save_document(calendar_client, page, document(block(text="New content")))
    assert saved.status_code == 200
    history = calendar_client.get(path + "/revisions").json()
    assert [row["version"] for row in history] == [2, 1]
    assert all("document" not in row for row in history)
    assert calendar_client.get(path + "/revisions/1").json()["document"] == original
    restore = path + "/revisions/1/restore"
    assert calendar_client.post(restore, json={"expected_version": 2}).status_code == 403
    assert (
        calendar_client.post(
            restore, headers=csrf_headers(calendar_client), json={"expected_version": 1}
        ).status_code
        == 409
    )
    result = calendar_client.post(
        restore, headers=csrf_headers(calendar_client), json={"expected_version": 2}
    )
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 3 and result.json()["document"] == original
    assert [row["version"] for row in calendar_client.get(path + "/revisions").json()] == [3, 2, 1]
    assert calendar_client.get(path + "/revisions/9999").status_code == 404
