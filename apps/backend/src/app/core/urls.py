from urllib.parse import urlsplit


def http_url(value: object) -> str:
    """Validate a stored HTTP link without fetching it."""
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Invalid HTTP URL.")
    try:
        value.encode("utf-8")
        parts = urlsplit(value)
        if (
            any(
                character.isspace() or ord(character) < 32 or ord(character) == 127
                for character in value
            )
            or "\\" in value
            or parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or (parts.port is not None and not 1 <= parts.port <= 65535)
        ):
            raise ValueError("Invalid HTTP URL.")
    except ValueError:
        raise ValueError("Invalid HTTP URL.") from None
    return value
