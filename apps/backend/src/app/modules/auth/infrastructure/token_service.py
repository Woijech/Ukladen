import secrets
from hashlib import sha256


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
