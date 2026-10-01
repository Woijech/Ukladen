from base64 import urlsafe_b64decode

import pytest

from app.modules.auth.application.ports import PasswordHasher
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.token_service import generate_token, hash_token


def test_argon2id_password_hashing() -> None:
    hasher: PasswordHasher = Argon2PasswordHasher()
    password = "correct horse battery staple 🔒"
    encoded = hasher.hash(password)
    assert encoded.startswith("$argon2id$")
    assert password not in encoded
    assert hasher.hash(password) != encoded
    assert hasher.verify(password, encoded)
    assert not hasher.verify(password + "wrong", encoded)


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "not-a-password-hash",
        "a" * 64,
        "$argon2id$v=19$m=invalid,t=3,p=4$salt$hash",
        "$argon2id$v=19$m=65536,t=3,p=4$bad$hash",
    ],
)
def test_invalid_password_hashes_are_rejected(encoded: str) -> None:
    assert not Argon2PasswordHasher().verify("test-password", encoded)


def test_opaque_token_generation_and_hashing() -> None:
    token = generate_token()
    other = generate_token()
    assert token != other
    assert len(token) == 43
    assert len(urlsafe_b64decode(token + "=")) == 32
    assert hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    digest = hash_token(token)
    assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")
    assert digest != token and digest != hash_token(other)
    assert hash_token(token) == digest
