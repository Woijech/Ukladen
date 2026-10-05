MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 4 * 1024 * 1024
AVATAR_SIZE = 512
AVATAR_CONTENT_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


class InvalidAvatar(ValueError):
    """The upload is not a supported, valid static image."""


class AvatarTooLarge(InvalidAvatar):
    """The upload exceeds the byte or decoded-pixel limit."""


class AvatarNotFound(Exception):
    """The current user has no available avatar."""
