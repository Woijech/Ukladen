from ipaddress import ip_address
from urllib.parse import urlsplit


def public_web_url(value: str) -> str:
    """Validate citation destinations; the application never fetches result URLs."""
    try:
        url = urlsplit(value)
        host = (url.hostname or "").encode("idna").decode("ascii").rstrip(".").lower()
        if (
            url.scheme not in {"http", "https"}
            or url.username is not None
            or url.password is not None
            or url.port not in {None, 80, 443}
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value
            or "%" in url.netloc
            or not host
            or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test"))
        ):
            raise ValueError()
        try:
            address = ip_address(host)
        except ValueError:
            labels = host.split(".")
            if (
                len(labels) < 2
                or not (labels[-1].isalpha() or labels[-1].startswith("xn--"))
                or any(
                    not label
                    or len(label) > 63
                    or label.startswith("-")
                    or label.endswith("-")
                    or not all(c.isalnum() or c == "-" for c in label)
                    for label in labels
                )
            ):
                raise ValueError() from None
        else:
            if not address.is_global or address.is_multicast:
                raise ValueError() from None
    except ValueError, UnicodeError:
        raise ValueError("A public HTTP(S) citation URL is required.") from None
    return value
