import json
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.workspace.application.transfer import WorkspaceTransfer, collect, page_order
from app.modules.workspace.domain.transfer import InvalidTransfer, PageSnapshot, WorkspaceArchive
from app.modules.workspace.presentation.transfer import TransferRequest


def archive(*pages: PageSnapshot) -> WorkspaceArchive:
    return WorkspaceArchive(format="ukladen.pages-databases", version=1, pages=pages, databases=())


def page(parent=None, identifier=None) -> PageSnapshot:
    return PageSnapshot(
        id=identifier or uuid4(),
        title="Page",
        parent_id=parent,
        document={"schema_version": 1, "blocks": []},
        trash_batch_id=None,
    )


def test_hierarchy_ids_depth_and_trash_batches_are_bounded() -> None:
    root = page()
    child = page(root.id)
    assert page_order(archive(child, root)) == [root, child]
    for invalid in (
        archive(root, root),
        archive(page(uuid4())),
        archive(replace(root, parent_id=child.id), child),
        archive(replace(root, trash_batch_id=uuid4())),
        archive(replace(root, trash_batch_id=root.id), child),
        archive(*(page() for _ in range(1001))),
    ):
        with pytest.raises(InvalidTransfer):
            page_order(invalid)
    chain = [root]
    for _ in range(64):
        chain.append(page(chain[-1].id))
    with pytest.raises(InvalidTransfer, match="64"):
        page_order(archive(*chain))


def test_digest_binds_owner_body_and_destination_and_export_never_truncates() -> None:
    owner = uuid4()
    original = archive(page())
    digest = WorkspaceTransfer.digest(owner, original, "Copy")
    assert digest != WorkspaceTransfer.digest(uuid4(), original, "Copy")
    assert digest != WorkspaceTransfer.digest(owner, original, "Other")
    assert digest != WorkspaceTransfer.digest(owner, archive(), "Copy")
    with pytest.raises(InvalidTransfer):
        collect(lambda limit, offset: list(range(offset, offset + limit)), 201)


def test_boundary_rejects_extra_fields_wrong_types_and_unknown_versions() -> None:
    valid = {
        "archive": {
            "format": "ukladen.pages-databases",
            "version": 1,
            "pages": [],
            "databases": [],
        },
        "title": "Copy",
    }
    assert TransferRequest.model_validate_json(json.dumps(valid)).archive.pages == ()
    for change in ({"version": 2}, {"user_id": str(uuid4())}, {"format": "foreign"}):
        raw = valid | {"archive": valid["archive"] | change}
        with pytest.raises(ValidationError):
            TransferRequest.model_validate_json(json.dumps(raw))
