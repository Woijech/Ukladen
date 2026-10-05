import logging
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from struct import pack
from unittest.mock import NonCallableMock, create_autospec
from uuid import uuid4
from zlib import crc32

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.modules.users.application.avatar import AvatarService
from app.modules.users.application.ports import (
    AvatarImageProcessor,
    AvatarStorage,
    AvatarStorageUnavailable,
    ProfileRepository,
)
from app.modules.users.domain.avatar import (
    MAX_AVATAR_BYTES,
    AvatarNotFound,
    AvatarTooLarge,
    InvalidAvatar,
)
from app.modules.users.domain.profile import ProfileUnavailable, UserProfile
from app.modules.users.infrastructure.avatar_image import PillowAvatarImageProcessor


def image_bytes(format: str = "PNG", size: tuple[int, int] = (64, 32), color: str = "red") -> bytes:
    image = Image.new("RGB", size, color)
    output = BytesIO()
    image.save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    "format, content_type", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_image_normalization(format: str, content_type: str) -> None:
    result = PillowAvatarImageProcessor().normalize(image_bytes(format), content_type)
    with Image.open(BytesIO(result)) as image:
        assert image.format == "PNG" and image.size == (512, 512)
        assert image.info == {} and not image.getexif()


def test_image_metadata_and_orientation_are_normalized() -> None:
    image = Image.new("RGB", (64, 32), "red")
    image.paste("blue", (32, 0, 64, 32))
    metadata = PngInfo()
    metadata.add_text("private-location", "secret")
    exif = Image.Exif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, format="PNG", pnginfo=metadata, exif=exif)
    result = PillowAvatarImageProcessor().normalize(output.getvalue(), "image/png")
    assert b"secret" not in result
    with Image.open(BytesIO(result)) as clean:
        assert not clean.info and not clean.getexif()
        assert clean.getpixel((256, 20)) == (255, 0, 0, 255)
        assert clean.getpixel((256, 490)) == (0, 0, 255, 255)


@pytest.mark.parametrize(
    "content, content_type",
    [
        (b"", "image/png"),
        (b"private-not-an-image", "image/png"),
        (b"<svg><script>alert(1)</script></svg>", "image/svg+xml"),
        (image_bytes(), "image/jpeg"),
        (image_bytes(), "application/octet-stream"),
        (image_bytes()[:40], "image/png"),
        (image_bytes("GIF"), "image/png"),
    ],
)
def test_invalid_images_are_rejected(content: bytes, content_type: str) -> None:
    with pytest.raises(InvalidAvatar):
        PillowAvatarImageProcessor().normalize(content, content_type)


def test_image_limits_and_animation() -> None:
    processor = PillowAvatarImageProcessor()
    with pytest.raises(AvatarTooLarge):
        processor.normalize(b"x" * (MAX_AVATAR_BYTES + 1), "image/png")
    with pytest.raises(AvatarTooLarge):
        processor.normalize(image_bytes(size=(3000, 1500)), "image/png")
    # A huge declared image is rejected before pixel decoding or allocation.
    png = bytearray(image_bytes())
    png[16:24] = pack(">II", 100000, 100000)
    png[29:33] = pack(">I", crc32(png[12:29]))
    with pytest.raises(AvatarTooLarge):
        processor.normalize(bytes(png), "image/png")
    frames = [Image.new("RGB", (16, 16), color) for color in ("red", "blue")]
    output = BytesIO()
    frames[0].save(output, format="PNG", save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(InvalidAvatar):
        processor.normalize(output.getvalue(), "image/png")


@pytest.fixture
def avatar_service() -> AvatarService:
    repository = create_autospec(ProfileRepository, instance=True)
    storage = create_autospec(AvatarStorage, instance=True)
    processor = create_autospec(AvatarImageProcessor, instance=True)
    now = datetime.now(UTC)
    profile = UserProfile(
        uuid4(),
        "student@example.com",
        None,
        "active",
        None,
        "UTC",
        "ru",
        now,
        now,
        avatar_key="previous-key",
    )
    repository.lock_active.return_value = profile
    repository.update_avatar.return_value = replace(profile, avatar_key="new-key")
    processor.normalize.return_value = b"normalized"
    return AvatarService(repository, storage, processor)


def test_avatar_service_ownership_and_cleanup(avatar_service: AvatarService) -> None:
    repository, storage, processor = (
        avatar_service.repository,
        avatar_service.storage,
        avatar_service.processor,
    )
    assert (
        isinstance(repository, NonCallableMock)
        and isinstance(storage, NonCallableMock)
        and isinstance(processor, NonCallableMock)
    )
    user_id = uuid4()
    prepared = avatar_service.prepare(user_id, b"upload", "image/png")
    assert prepared.key.startswith(f"avatars/{user_id}/") and prepared.key.endswith(".png")
    assert b"normalized".decode() not in repr(prepared)
    result = avatar_service.replace(user_id, prepared)
    repository.lock_active.assert_called_once_with(user_id)
    storage.put.assert_called_once_with(prepared.key, b"normalized")
    repository.update_avatar.assert_called_once_with(user_id, prepared.key)
    assert result.previous_key == "previous-key"
    storage.delete.assert_not_called()
    storage.get.return_value = b"download"
    assert avatar_service.get(user_id) == b"download"
    storage.get.assert_called_once_with("previous-key")
    assert avatar_service.remove(user_id) == "previous-key"
    assert repository.update_avatar.call_args.args == (user_id, None)
    avatar_service.cleanup(result.previous_key)
    storage.delete.assert_called_once_with("previous-key")


def test_inactive_and_absent_avatars(avatar_service: AvatarService) -> None:
    repository, storage = avatar_service.repository, avatar_service.storage
    assert isinstance(repository, NonCallableMock) and isinstance(storage, NonCallableMock)
    user_id = uuid4()
    repository.lock_active.return_value = None
    prepared = avatar_service.prepare(user_id, b"upload", "image/png")
    for operation in (
        lambda: avatar_service.get(user_id),
        lambda: avatar_service.remove(user_id),
        lambda: avatar_service.replace(user_id, prepared),
    ):
        with pytest.raises(ProfileUnavailable):
            operation()
    storage.put.assert_not_called()
    storage.get.assert_not_called()
    storage.delete.assert_not_called()


def test_cleanup_failure_is_safe_and_ambiguous_commits_keep_live_object(
    avatar_service: AvatarService,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        logging.getLogger("app.modules.users.application.avatar"), "disabled", False
    )
    storage = avatar_service.storage
    assert isinstance(storage, NonCallableMock)
    storage.delete.side_effect = AvatarStorageUnavailable("private-error-details")
    avatar_service.cleanup("old-key")
    assert "Avatar cleanup failed." in caplog.text and "private" not in caplog.text
    recovery = create_autospec(ProfileRepository, instance=True)
    recovery.lock_avatar_key.return_value = "new-key"
    storage.delete.reset_mock()
    avatar_service.cleanup_failed_upload(uuid4(), "new-key", recovery)
    storage.delete.assert_not_called()
    recovery.lock_avatar_key.return_value = "old-key"
    avatar_service.cleanup_failed_upload(uuid4(), "new-key", recovery)
    storage.delete.assert_called_once_with("new-key")


def test_removing_absent_avatar_does_not_write(avatar_service: AvatarService) -> None:
    repository, storage = avatar_service.repository, avatar_service.storage
    assert isinstance(repository, NonCallableMock) and isinstance(storage, NonCallableMock)
    profile = repository.lock_active.return_value
    repository.lock_active.return_value = replace(profile, avatar_key=None)
    assert avatar_service.remove(uuid4()) is None
    repository.update_avatar.assert_not_called()
    with pytest.raises(AvatarNotFound):
        avatar_service.get(uuid4())
    storage.get.assert_not_called()
