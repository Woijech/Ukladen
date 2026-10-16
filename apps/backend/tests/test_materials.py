from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.modules.materials.application.ports import MaterialRepository, MaterialStorage
from app.modules.materials.application.service import MaterialService
from app.modules.materials.domain.materials import (
    MAX_FILE_BYTES,
    InvalidMaterialInput,
    MaterialTooLarge,
    StorageQuotaExceeded,
    file_metadata,
    material_title,
    material_url,
)
from app.modules.users.application.ports import UserAuthentication


@pytest.mark.parametrize(
    "filename,size,error",
    [
        ("../file.pdf", 1, InvalidMaterialInput),
        ("x\\file.pdf", 1, InvalidMaterialInput),
        ("x.doc", 1, InvalidMaterialInput),
        ("x.ppt", 1, InvalidMaterialInput),
        ("x.jpg", 1, InvalidMaterialInput),
        ("x.pdf", True, InvalidMaterialInput),
        ("x.pdf", 0, InvalidMaterialInput),
        ("x.pdf", MAX_FILE_BYTES + 1, MaterialTooLarge),
    ],
)
def test_file_boundaries(filename, size, error) -> None:
    with pytest.raises(error):
        file_metadata(filename, size)


def test_file_maximum_and_unfetched_link_validation() -> None:
    assert file_metadata("Lectures.PDF", MAX_FILE_BYTES) == (
        "Lectures.PDF",
        "application/pdf",
        MAX_FILE_BYTES,
    )
    assert material_url("https://example.com/lecture.pdf") == "https://example.com/lecture.pdf"
    for url in ("file:///etc/passwd", "https://user:password@example.com", "javascript:alert(1)"):
        with pytest.raises(InvalidMaterialInput):
            material_url(url)
    for title in (" ", "x\x00y", "x\r\ny", "x" * 201):
        with pytest.raises(InvalidMaterialInput):
            material_title(title)


def test_quota_rejection_never_touches_storage() -> None:
    repository, users, storage = (
        Mock(spec=MaterialRepository),
        Mock(spec=UserAuthentication),
        Mock(spec=MaterialStorage),
    )
    repository.usage.return_value = (1024**3, 100)
    service = MaterialService(repository, users, storage)
    with pytest.raises(StorageQuotaExceeded):
        service.create_upload(uuid4(), "study.txt", 1)
    assert storage.mock_calls == []
    repository.create.assert_not_called()
