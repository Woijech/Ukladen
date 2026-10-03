import logging
import os
from collections.abc import Iterator
from http.cookies import SimpleCookie
from unittest.mock import Mock, create_autospec
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis import Redis
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_auth_http import database as database
from test_auth_http import issued as issued
from test_auth_http import limiter as limiter
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.db.session import create_session_factory
from app.main import create_app
from app.modules.auth.application.dto import (
    GoogleAuthorization,
    IssuedSession,
    VerifiedGoogleIdentity,
)
from app.modules.auth.application.google_login import GoogleLoginService
from app.modules.auth.application.google_oauth import GoogleOAuthService
from app.modules.auth.application.oauth_state import OAuthStateService
from app.modules.auth.application.ports import (
    ExternalIdentityProvider,
    ExternalIdentityUnavailable,
    OAuthStateUnavailable,
    RateLimiterUnavailable,
)
from app.modules.auth.domain.errors import (
    AccountLinkingRequired,
    InvalidExternalIdentity,
    InvalidOAuthState,
)
from app.modules.auth.infrastructure.orm import CredentialModel, IdentityModel, SessionModel
from app.modules.auth.infrastructure.request_protection import auth_access_log_filter
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.auth.presentation.dependencies import (
    get_database,
    get_google_login,
    get_google_oauth,
)
from app.modules.users.infrastructure.orm import UserModel

ORIGIN = "https://testserver"
START = "/api/v1/auth/google/start"
CALLBACK = "/api/v1/auth/google/callback"
IDENTITY = VerifiedGoogleIdentity("google-subject", "student@example.com")


@pytest.fixture
def google_settings(settings: Settings) -> Settings:
    return Settings.model_validate(
        settings.model_dump()
        | {
            "google_client_id": "test-client",
            "google_client_secret": "test-secret",
            "google_redirect_uri": ORIGIN + CALLBACK,
            "frontend_auth_success_url": ORIGIN + "/success",
            "frontend_auth_error_url": ORIGIN + "/error",
            "auth_allowed_origins": [ORIGIN],
        }
    )


@pytest.fixture
def oauth() -> Mock:
    oauth = create_autospec(GoogleOAuthService, instance=True)
    oauth.start.return_value = GoogleAuthorization(
        "https://accounts.google.com/authorize?state=test", generate_token()
    )
    oauth.resolve_callback.return_value = IDENTITY
    return oauth


@pytest.fixture
def accounts(issued: IssuedSession) -> Mock:
    accounts = create_autospec(GoogleLoginService, instance=True)
    accounts.login.return_value = issued
    return accounts


@pytest.fixture
def client(
    google_settings: Settings, oauth: Mock, accounts: Mock, database: Mock, limiter: Mock
) -> Iterator[TestClient]:
    application = create_app(google_settings)
    application.dependency_overrides[get_google_oauth] = lambda: oauth
    application.dependency_overrides[get_google_login] = lambda: accounts
    application.dependency_overrides[get_database] = lambda: database
    with TestClient(
        application, base_url=ORIGIN, follow_redirects=False, client=("192.0.2.10", 5000)
    ) as client:
        application.state.rate_limiter = limiter
        yield client


def test_start_and_committed_callback_cookie_flags(
    client: TestClient,
    google_settings: Settings,
    oauth: Mock,
    issued: IssuedSession,
    accounts: Mock,
    database: Mock,
) -> None:
    response = client.get(START)
    assert response.status_code == 303 and response.headers["location"].startswith(
        "https://accounts.google.com/"
    )
    cookie = SimpleCookie(response.headers["set-cookie"])[google_settings.auth_oauth_cookie_name]
    assert cookie["secure"] and cookie["httponly"] and cookie["samesite"] == "lax"
    assert cookie["path"] == "/" and not cookie["domain"] and cookie["max-age"] == "600"
    state = generate_token()

    def after_commit(*args: object) -> None:
        assert not client.cookies.get(google_settings.auth_session_cookie_name)

    database.begin.return_value.__exit__.side_effect = after_commit
    response = client.get(
        CALLBACK,
        params={"state": state, "code": "private-code"},
        headers={"User-Agent": "google-test"},
    )
    assert response.status_code == 303 and response.headers["location"] == ORIGIN + "/success"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert client.cookies.get(google_settings.auth_session_cookie_name) == issued.token
    assert client.cookies.get(google_settings.auth_oauth_cookie_name) is None
    oauth.resolve_callback.assert_called_once_with(
        state=state,
        code="private-code",
        error=None,
        browser_token=oauth.start.return_value.browser_token,
    )
    assert accounts.login.call_args.args == (IDENTITY,)


@pytest.mark.parametrize("failure", ["state", "identity", "linking", "provider", "redis", "commit"])
def test_callback_failures_preserve_session_and_hide_secrets(
    client: TestClient,
    oauth: Mock,
    accounts: Mock,
    database: Mock,
    google_settings: Settings,
    failure: str,
) -> None:
    client.get(START)
    existing = generate_token()
    client.cookies.set(google_settings.auth_session_cookie_name, existing)
    errors = {
        "state": InvalidOAuthState,
        "identity": InvalidExternalIdentity,
        "linking": AccountLinkingRequired,
        "provider": ExternalIdentityUnavailable,
        "redis": OAuthStateUnavailable,
        "commit": SQLAlchemyError,
    }
    if failure == "commit":
        database.begin.return_value.__exit__.side_effect = SQLAlchemyError("private-code")
    elif failure == "linking":
        accounts.login.side_effect = errors[failure]("private-code")
    else:
        oauth.resolve_callback.side_effect = errors[failure]("private-code")
    response = client.get(CALLBACK, params={"state": generate_token(), "code": "private-code"})
    assert response.status_code == 303 and response.headers["location"] == ORIGIN + "/error"
    assert "private-code" not in response.text + str(response.headers)
    assert "set-cookie" not in response.headers
    assert client.cookies.get(google_settings.auth_session_cookie_name) == existing
    if failure not in {"commit", "linking"}:
        accounts.login.assert_not_called()


@pytest.mark.parametrize(
    "query",
    [
        "state=short&code=private-code",
        "state=" + "x" * 43 + "&state=" + "y" * 43 + "&code=private-code",
        "code=" + "x" * 4097,
    ],
)
def test_invalid_queries_stop_before_oauth(client: TestClient, oauth: Mock, query: str) -> None:
    response = client.get(CALLBACK + "?" + query)
    assert response.status_code == 303 and response.headers["location"] == ORIGIN + "/error"
    oauth.resolve_callback.assert_not_called()


@pytest.mark.parametrize(
    "headers", [{"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://evil.example"}]
)
def test_start_rejects_cross_site_navigation(
    client: TestClient, oauth: Mock, headers: dict[str, str]
) -> None:
    assert client.get(START, headers=headers).status_code == 403
    oauth.start.assert_not_called()


@pytest.mark.parametrize("path", [START, CALLBACK])
@pytest.mark.parametrize("outage", [False, True])
def test_google_rate_limits(client: TestClient, limiter: Mock, path: str, outage: bool) -> None:
    if outage:
        limiter.check.side_effect = RateLimiterUnavailable("private-details")
    else:
        limiter.check.return_value = (False, 12)
    response = client.get(path)
    assert response.status_code == (503 if outage else 429)
    assert "private" not in response.text
    assert "set-cookie" not in response.headers
    prefix = "google-start" if path == START else "google-callback"
    limiter.check.assert_called_once_with(f"{prefix}:{hash_token('192.0.2.10')}", 10, 60)


def test_disabled_browser_google_has_no_provider_io(settings: Settings, limiter: Mock) -> None:
    application = create_app(settings)
    with TestClient(application, base_url=ORIGIN, follow_redirects=False) as client:
        application.state.rate_limiter = limiter
        assert application.state.google_provider is None
        assert client.get(START).status_code == 503
        assert client.get(CALLBACK).status_code == 503


@pytest.mark.parametrize(
    "change",
    [
        {"frontend_auth_error_url": None},
        {"frontend_auth_success_url": "http://evil.example/"},
        {"frontend_auth_success_url": "https://user:secret@example.com/"},
        {"frontend_auth_success_url": "https://example.com/?token=private"},
        {"auth_oauth_cookie_name": "__Host-ukladen_session"},
        {
            "auth_cookie_secure": False,
            "auth_session_cookie_name": "session",
            "auth_csrf_cookie_name": "csrf",
        },
        {"auth_google_start_rate_limit": 0},
    ],
)
def test_invalid_browser_google_settings(
    google_settings: Settings, change: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(google_settings.model_dump() | change)


def test_callback_access_logs_drop_query_and_keep_metadata() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "test",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("peer", "GET", CALLBACK + "?code=private&state=secret", "1.1", 303),
        None,
    )
    assert auth_access_log_filter.filter(record)
    message = record.getMessage()
    assert "private" not in message and "secret" not in message
    assert CALLBACK in message and "303" in message


def test_oauth_service_consumes_state_before_provider(settings: Settings) -> None:
    states = create_autospec(OAuthStateService, instance=True)
    provider = create_autospec(ExternalIdentityProvider, instance=True)
    parent = Mock()
    parent.attach_mock(states, "states")
    parent.attach_mock(provider, "provider")
    states.consume.side_effect = InvalidOAuthState("Invalid state")
    with pytest.raises(InvalidOAuthState):
        GoogleOAuthService(states, provider).resolve_callback(
            state=None, browser_token=None, code="code"
        )
    provider.resolve_callback.assert_not_called()
    states.consume.side_effect = None
    with pytest.raises(InvalidExternalIdentity):
        GoogleOAuthService(states, provider).resolve_callback(
            state=generate_token(), browser_token=generate_token(), code=None, error="access_denied"
        )
    provider.resolve_callback.assert_not_called()


@pytest.fixture
def provider() -> Mock:
    provider = create_autospec(ExternalIdentityProvider, instance=True)
    provider.build_authorization_url.side_effect = lambda **params: (
        "https://accounts.google.com/authorize?" + urlencode(params)
    )
    provider.resolve_callback.return_value = IDENTITY
    return provider


@pytest.fixture
def live_client(
    concurrent_engine: Engine, google_settings: Settings, provider: Mock, limiter: Mock
) -> Iterator[TestClient]:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL for Google HTTP integration checks.")
    redis = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    application = create_app(google_settings)
    try:
        with TestClient(
            application, base_url=ORIGIN, follow_redirects=False, client=("192.0.2.10", 5000)
        ) as client:
            application.state.session_factory = create_session_factory(concurrent_engine)
            application.state.redis = redis
            application.state.rate_limiter = limiter
            application.state.google_provider = provider
            yield client
    finally:
        with Session(concurrent_engine) as database:
            keys = [
                f"ukladen:auth:session:{h}"
                for h in database.scalars(select(SessionModel.token_hash))
            ]
        keys += [
            f"ukladen:auth:oauth:{hash_token(call.kwargs['state'])}"
            for call in provider.build_authorization_url.call_args_list
        ]
        if keys:
            redis.delete(*keys)
        redis.close()


def start(client: TestClient) -> str:
    response = client.get(START)
    assert response.status_code == 303
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def test_live_login_replay_and_session_revocation(
    live_client: TestClient, concurrent_engine: Engine, google_settings: Settings, provider: Mock
) -> None:
    state = start(live_client)
    response = live_client.get(
        CALLBACK,
        params={"state": state, "code": "test-code"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.headers["location"] == ORIGIN + "/success"
    token = live_client.cookies.get(google_settings.auth_session_cookie_name)
    assert token
    with Session(concurrent_engine) as database:
        user = database.scalar(select(UserModel))
        identity = database.scalar(select(IdentityModel))
        session = database.scalar(select(SessionModel))
        assert user and user.email_verified_at and identity and identity.user_id == user.id
        assert session and session.token_hash == hash_token(token)
        assert database.scalar(select(func.count()).select_from(CredentialModel)) == 0
    assert live_client.get("/api/v1/auth/sessions").status_code == 200
    assert (
        live_client.get(CALLBACK, params={"state": state, "code": "test-code"}).headers["location"]
        == ORIGIN + "/error"
    )
    assert provider.resolve_callback.call_count == 1
    csrf = live_client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert (
        live_client.post(
            "/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
        ).status_code
        == 204
    )


@pytest.mark.parametrize("failure", ["collision", "provider", "wrong-browser", "denial"])
def test_live_failure_never_creates_accounts_or_sessions(
    live_client: TestClient,
    concurrent_engine: Engine,
    google_settings: Settings,
    provider: Mock,
    failure: str,
) -> None:
    if failure == "collision":
        with Session(concurrent_engine) as database, database.begin():
            database.add(UserModel(email=IDENTITY.email))
    state = start(live_client)
    if failure == "provider":
        provider.resolve_callback.side_effect = ExternalIdentityUnavailable("private details")
    elif failure == "wrong-browser":
        live_client.cookies.clear()
    params = (
        {"state": state, "code": "test-code"}
        if failure != "denial"
        else {"state": state, "error": "access_denied"}
    )
    assert live_client.get(CALLBACK, params=params).headers["location"] == ORIGIN + "/error"
    assert not live_client.cookies.get(google_settings.auth_session_cookie_name)
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(UserModel)) == (
            failure == "collision"
        )
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 0
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 0
    if failure in {"wrong-browser", "denial"}:
        provider.resolve_callback.assert_not_called()
