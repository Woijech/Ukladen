import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.dto import VerifiedGoogleIdentity
from app.modules.auth.application.ports import ExternalIdentityProvider, ExternalIdentityUnavailable
from app.modules.auth.domain.errors import InvalidExternalIdentity
from app.modules.auth.infrastructure.google_oidc import DISCOVERY_URL, GoogleOidcProvider
from app.modules.auth.infrastructure.token_service import generate_token

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
CLIENT_ID = "test-client.apps.googleusercontent.com"
SECRET = "synthetic-google-client-secret"
CODE = "synthetic-authorization-code"
NONCE = generate_token()
VERIFIER = generate_token()


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(key: rsa.RSAPrivateKey, kid: str = "test-key") -> dict[str, Any]:
    return RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


@pytest.fixture
def google_settings(settings: Settings) -> Settings:
    return Settings.model_validate(
        settings.model_dump()
        | {
            "google_client_id": CLIENT_ID,
            "google_client_secret": SECRET,
            "google_redirect_uri": "https://ukladen.example/api/v1/auth/google/callback",
        }
    )


@pytest.fixture
def claims() -> dict[str, Any]:
    now = int(datetime.now(UTC).timestamp())
    return {
        "iss": "https://accounts.google.com",
        "sub": "Google-Subject-123",
        "aud": CLIENT_ID,
        "iat": now - 30,
        "exp": now + 600,
        "nonce": NONCE,
        "email": "  Student@EXAMPLE.COM  ",
        "email_verified": True,
    }


def signed_token(claims: dict[str, Any], key: rsa.RSAPrivateKey, kid: str = "test-key") -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def responses(claims: dict[str, Any], private_key: rsa.RSAPrivateKey) -> dict[str, httpx.Response]:
    return {
        DISCOVERY_URL: httpx.Response(
            200,
            json={
                "issuer": "https://accounts.google.com",
                "authorization_endpoint": AUTH_URL,
                "token_endpoint": TOKEN_URL,
                "jwks_uri": KEYS_URL,
                "id_token_signing_alg_values_supported": ["RS256"],
                "code_challenge_methods_supported": ["S256"],
            },
            headers={"Cache-Control": "public, max-age=600"},
        ),
        KEYS_URL: httpx.Response(
            200,
            json={"keys": [public_jwk(private_key)]},
            headers={"Cache-Control": "public, max-age=600"},
        ),
        TOKEN_URL: httpx.Response(
            200,
            json={
                "id_token": signed_token(claims, private_key),
                "access_token": "synthetic-access-token",
                "refresh_token": "synthetic-refresh-token",
            },
        ),
    }


@pytest.fixture
def requests() -> list[httpx.Request]:
    return []


@pytest.fixture
def clock() -> Mock:
    return Mock(return_value=100.0)


@pytest.fixture
def provider(
    google_settings: Settings,
    responses: dict[str, httpx.Response],
    requests: list[httpx.Request],
    clock: Mock,
) -> Iterator[GoogleOidcProvider]:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) in responses  # No external network is reachable in these tests.
        return responses[str(request.url)]

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        yield GoogleOidcProvider(google_settings, client, clock=clock)


def resolve(provider: ExternalIdentityProvider) -> VerifiedGoogleIdentity:
    return provider.resolve_callback(code=CODE, code_verifier=VERIFIER, nonce=NONCE)


def test_authorization_and_signed_identity_use_only_expected_transport(
    provider: GoogleOidcProvider,
    google_settings: Settings,
    requests: list[httpx.Request],
    caplog: pytest.LogCaptureFixture,
) -> None:
    state, challenge = generate_token(), generate_token()
    with caplog.at_level(logging.DEBUG):
        url = provider.build_authorization_url(state=state, nonce=NONCE, code_challenge=challenge)
        identity = resolve(provider)
    assert identity == VerifiedGoogleIdentity("Google-Subject-123", "student@example.com")
    assert urlsplit(url)._replace(query="").geturl() == AUTH_URL
    assert parse_qs(urlsplit(url).query) == {
        "client_id": [CLIENT_ID],
        "redirect_uri": [str(google_settings.google_redirect_uri)],
        "response_type": ["code"],
        "scope": ["openid email"],
        "state": [state],
        "nonce": [NONCE],
        "code_challenge": [challenge],
        "code_challenge_method": ["S256"],
    }
    post = next(request for request in requests if request.method == "POST")
    assert str(post.url) == TOKEN_URL and not post.url.query
    assert parse_qs(post.content.decode()) == {
        "code": [CODE],
        "client_id": [CLIENT_ID],
        "client_secret": [SECRET],
        "redirect_uri": [str(google_settings.google_redirect_uri)],
        "grant_type": ["authorization_code"],
        "code_verifier": [VERIFIER],
    }
    assert [str(request.url) for request in requests] == [DISCOVERY_URL, TOKEN_URL, KEYS_URL]
    for request in requests:
        assert all(value == 3 for value in request.extensions["timeout"].values())
    for secret in (SECRET, CODE, "synthetic-access-token", "synthetic-refresh-token"):
        assert secret not in caplog.text and secret not in repr(identity)
    assert list(provider._documents) == [DISCOVERY_URL, KEYS_URL]
    assert CODE not in repr(provider._documents)
    assert all("id_token" not in document for _, document in provider._documents.values())
    assert not provider.client.is_closed


@pytest.mark.parametrize(
    "update",
    [
        {"iss": "https://attacker.example"},
        {"aud": "another-client"},
        {"aud": [CLIENT_ID]},
        {"azp": "another-client"},
        {"exp": 0},
        {"iat": 99999999999},
        {"exp": "99999999999"},
        {"iat": True},
        {"email_verified": False},
        {"email_verified": "true"},
        {"email_verified": 1},
        {"email": "Name <student@example.com>"},
        {"email": 123},
        {"nonce": generate_token()},
        {"nonce": "Я" * 43},
        {"nonce": None},
        {"sub": ""},
        {"sub": 123},
        {"sub": "x" * 256},
        {"sub": "subject\nvalue"},
    ],
)
def test_signed_invalid_claims_are_rejected(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    claims: dict[str, Any],
    private_key: rsa.RSAPrivateKey,
    update: dict[str, Any],
) -> None:
    responses[TOKEN_URL] = httpx.Response(
        200, json={"id_token": signed_token(claims | update, private_key)}
    )
    with pytest.raises(InvalidExternalIdentity, match="^Invalid external identity\\.$") as error:
        resolve(provider)
    assert SECRET not in str(error.value) and CODE not in str(error.value)


@pytest.mark.parametrize(
    "missing", ["iss", "sub", "aud", "iat", "exp", "nonce", "email", "email_verified"]
)
def test_required_claims_cannot_be_missing(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    claims: dict[str, Any],
    private_key: rsa.RSAPrivateKey,
    missing: str,
) -> None:
    claims.pop(missing)
    responses[TOKEN_URL] = httpx.Response(200, json={"id_token": signed_token(claims, private_key)})
    with pytest.raises(InvalidExternalIdentity):
        resolve(provider)


def test_legacy_google_issuer_and_matching_azp_are_accepted(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    claims: dict[str, Any],
    private_key: rsa.RSAPrivateKey,
) -> None:
    responses[TOKEN_URL] = httpx.Response(
        200,
        json={
            "id_token": signed_token(
                claims | {"iss": "accounts.google.com", "azp": CLIENT_ID}, private_key
            )
        },
    )
    assert resolve(provider).subject == claims["sub"]


@pytest.mark.parametrize(
    "kind",
    [
        "wrong_signature",
        "hs256",
        "none",
        "no_kid",
        "malformed",
        "oversized",
        "missing",
        "wrong_type",
    ],
)
def test_invalid_token_or_algorithm_never_establishes_identity(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    claims: dict[str, Any],
    private_key: rsa.RSAPrivateKey,
    kind: str,
) -> None:
    if kind == "wrong_signature":
        token: object = signed_token(
            claims, rsa.generate_private_key(public_exponent=65537, key_size=2048)
        )
    elif kind in {"hs256", "none"}:
        token = jwt.encode(
            claims,
            "a" * 32 if kind == "hs256" else "",
            algorithm="HS256" if kind == "hs256" else "none",
            headers={"kid": "test-key"},
        )
    elif kind == "no_kid":
        token = jwt.encode(claims, private_key, algorithm="RS256")
    else:
        token = {
            "malformed": "invalid.jwt.token",
            "oversized": "x" * 16385,
            "missing": None,
            "wrong_type": 123,
        }[kind]
    responses[TOKEN_URL] = httpx.Response(200, json={"id_token": token})
    with pytest.raises(InvalidExternalIdentity):
        resolve(provider)


@pytest.mark.parametrize("field", ["state", "nonce", "code_challenge"])
def test_authorization_inputs_are_validated_before_io(
    provider: GoogleOidcProvider, requests: list[httpx.Request], field: str
) -> None:
    inputs = {"state": generate_token(), "nonce": NONCE, "code_challenge": generate_token()} | {
        field: "!" * 43
    }
    with pytest.raises(InvalidExternalIdentity):
        provider.build_authorization_url(**inputs)
    assert not requests


@pytest.mark.parametrize(
    "inputs",
    [
        {"code": ""},
        {"code": "x" * 4097},
        {"code_verifier": "short"},
        {"code_verifier": "!" * 43},
        {"nonce": ""},
    ],
)
def test_callback_inputs_are_validated_before_io(
    provider: GoogleOidcProvider, requests: list[httpx.Request], inputs: dict[str, str]
) -> None:
    with pytest.raises(InvalidExternalIdentity):
        provider.resolve_callback(
            **({"code": CODE, "code_verifier": VERIFIER, "nonce": NONCE} | inputs)
        )
    assert not requests


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", "https://attacker.example"),
        ("id_token_signing_alg_values_supported", None),
        ("code_challenge_methods_supported", ["plain"]),
        ("authorization_endpoint", "https://attacker.example/auth"),
        ("token_endpoint", "http://oauth2.googleapis.com/token"),
        ("token_endpoint", "https://oauth2.googleapis.com@attacker.example/token"),
        ("token_endpoint", "https://oauth2.googleapis.com:443/token"),
        ("jwks_uri", "https://www.googleapis.com/keys?secret=leak"),
        ("jwks_uri", "https://www.googleapis.com/keys#fragment"),
        ("jwks_uri", 123),
    ],
)
def test_discovery_rejects_unsafe_endpoints_or_metadata(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    requests: list[httpx.Request],
    field: str,
    value: object,
) -> None:
    responses[DISCOVERY_URL] = httpx.Response(
        200, json=responses[DISCOVERY_URL].json() | {field: value}
    )
    with pytest.raises(ExternalIdentityUnavailable):
        resolve(provider)
    assert [str(request.url) for request in requests] == [DISCOVERY_URL]


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, InvalidExternalIdentity),
        (401, InvalidExternalIdentity),
        (429, ExternalIdentityUnavailable),
        (500, ExternalIdentityUnavailable),
        (302, ExternalIdentityUnavailable),
    ],
)
def test_token_http_failures_are_fixed_and_not_retried(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    requests: list[httpx.Request],
    status: int,
    expected: type[Exception],
) -> None:
    responses[TOKEN_URL] = httpx.Response(
        status, text=CODE + SECRET, headers={"Location": "https://attacker.example"}
    )
    with pytest.raises(expected) as error:
        resolve(provider)
    assert CODE not in str(error.value) and SECRET not in str(error.value)
    assert sum(request.method == "POST" for request in requests) == 1
    assert len(requests) == 2


@pytest.mark.parametrize("endpoint", [DISCOVERY_URL, TOKEN_URL, KEYS_URL])
@pytest.mark.parametrize("payload", [b"not-json", b"[]", b"x" * 65537])
def test_malformed_provider_json_is_sanitized(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    endpoint: str,
    payload: bytes,
) -> None:
    responses[endpoint] = httpx.Response(200, content=payload)
    with pytest.raises(
        ExternalIdentityUnavailable, match="^External identity provider is unavailable\\.$"
    ):
        resolve(provider)


def test_transport_errors_suppress_secret_exception_context(google_settings: Settings) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(SECRET + CODE)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        provider = GoogleOidcProvider(google_settings, client)
        with pytest.raises(ExternalIdentityUnavailable) as error:
            resolve(provider)
    assert error.value.__suppress_context__ and SECRET not in str(error.value)


@pytest.mark.parametrize(
    "update",
    [
        {"kty": "oct"},
        {"alg": "HS256"},
        {"use": "enc"},
        {"key_ops": ["sign"]},
        {"d": "private-material"},
    ],
)
def test_inappropriate_signing_keys_are_rejected(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    private_key: rsa.RSAPrivateKey,
    update: dict[str, Any],
) -> None:
    responses[KEYS_URL] = httpx.Response(200, json={"keys": [public_jwk(private_key) | update]})
    with pytest.raises(InvalidExternalIdentity):
        resolve(provider)


def test_unknown_kid_refreshes_keys_once_and_accepts_rotation(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    requests: list[httpx.Request],
    claims: dict[str, Any],
    private_key: rsa.RSAPrivateKey,
) -> None:
    resolve(provider)
    requests.clear()
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    responses[TOKEN_URL] = httpx.Response(
        200, json={"id_token": signed_token(claims, rotated, "rotated-key")}
    )
    responses[KEYS_URL] = httpx.Response(
        200,
        json={"keys": [public_jwk(rotated, "rotated-key")]},
        headers={"Cache-Control": "max-age=600"},
    )
    assert resolve(provider).email == "student@example.com"
    assert [str(request.url) for request in requests] == [TOKEN_URL, KEYS_URL]
    responses[TOKEN_URL] = httpx.Response(
        200, json={"id_token": signed_token(claims, private_key, "missing-key")}
    )
    requests.clear()
    with pytest.raises(InvalidExternalIdentity):
        resolve(provider)
    assert [str(request.url) for request in requests] == [TOKEN_URL, KEYS_URL]


@pytest.mark.parametrize(
    "keys,expected",
    [
        (None, ExternalIdentityUnavailable),
        ([123], ExternalIdentityUnavailable),
        ([{"kid": "test-key", "kty": "RSA"}], ExternalIdentityUnavailable),
        ("duplicate", InvalidExternalIdentity),
    ],
)
def test_malformed_or_ambiguous_key_sets_fail_closed(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    private_key: rsa.RSAPrivateKey,
    keys: object,
    expected: type[Exception],
) -> None:
    if keys == "duplicate":
        keys = [public_jwk(private_key), public_jwk(private_key)]
    responses[KEYS_URL] = httpx.Response(200, json={"keys": keys})
    with pytest.raises(expected):
        resolve(provider)


@pytest.mark.parametrize(
    "headers,expiry",
    [
        ({"Cache-Control": "max-age=600", "Age": "100"}, 600),
        ({"Cache-Control": "max-age=600, no-store"}, 100),
        ({"Cache-Control": "no-cache, max-age=600"}, 100),
        ({}, 100),
        ({"Cache-Control": "max-age=999999"}, 3700),
    ],
)
def test_public_document_cache_honors_expiry(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    requests: list[httpx.Request],
    clock: Mock,
    headers: dict[str, str],
    expiry: int,
) -> None:
    responses[DISCOVERY_URL] = httpx.Response(
        200, json=responses[DISCOVERY_URL].json(), headers=headers
    )
    resolve(provider)
    if expiry > 100:
        assert provider._documents[DISCOVERY_URL][0] == expiry
    else:
        assert DISCOVERY_URL not in provider._documents
    clock.return_value = expiry
    requests.clear()
    resolve(provider)
    assert DISCOVERY_URL in [str(request.url) for request in requests]


def test_public_document_cache_reuses_fresh_discovery_and_keys(
    provider: GoogleOidcProvider, requests: list[httpx.Request]
) -> None:
    resolve(provider)
    requests.clear()
    resolve(provider)
    assert [str(request.url) for request in requests] == [TOKEN_URL]


@pytest.mark.parametrize(
    "update",
    [
        {"google_client_id": CLIENT_ID},
        {"google_client_id": ""},
        {"google_redirect_uri": "http://attacker.example/callback"},
        {"google_redirect_uri": "https://user:password@ukladen.example/callback"},
        {"google_redirect_uri": "https://ukladen.example/callback?redirect=attacker"},
        {"google_redirect_uri": "https://ukladen.example/callback#fragment"},
    ],
)
def test_google_configuration_rejects_partial_and_unsafe_values(
    settings: Settings, google_settings: Settings, update: dict[str, object]
) -> None:
    base = settings if update.keys() == {"google_client_id"} else google_settings
    with pytest.raises(ValidationError) as error:
        Settings.model_validate(base.model_dump() | update)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost:8080/api/v1/auth/google/callback",
        "http://127.0.0.1/callback",
        "http://[::1]:8080/callback",
    ],
)
def test_local_callback_configuration_is_allowed(google_settings: Settings, uri: str) -> None:
    assert Settings.model_validate(
        google_settings.model_dump() | {"google_redirect_uri": uri}
    ).google_redirect_uri
    assert SECRET not in repr(google_settings)


def test_disabled_provider_has_no_io(settings: Settings) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected I/O"))
    ) as client:
        with pytest.raises(ExternalIdentityUnavailable):
            GoogleOidcProvider(settings, client)


@pytest.mark.parametrize(
    "headers", [{"crit": ["unknown"]}, {"jku": "https://attacker.example/keys"}]
)
def test_token_header_cannot_override_verification_rules(
    provider: GoogleOidcProvider,
    responses: dict[str, httpx.Response],
    claims: dict[str, Any],
    private_key: rsa.RSAPrivateKey,
    headers: dict[str, Any],
) -> None:
    responses[TOKEN_URL] = httpx.Response(
        200,
        json={
            "id_token": jwt.encode(
                claims, private_key, algorithm="RS256", headers={"kid": "test-key"} | headers
            )
        },
    )
    if "crit" in headers:
        with pytest.raises(InvalidExternalIdentity):
            resolve(provider)
    else:
        assert resolve(provider).subject == claims["sub"]


def test_weak_public_key_cannot_authenticate(
    provider: GoogleOidcProvider, responses: dict[str, httpx.Response]
) -> None:
    weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    responses[KEYS_URL] = httpx.Response(200, json={"keys": [public_jwk(weak)]})
    with pytest.raises((InvalidExternalIdentity, ExternalIdentityUnavailable)):
        resolve(provider)
