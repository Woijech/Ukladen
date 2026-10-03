import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from ipaddress import ip_address
from threading import Barrier
from unittest.mock import Mock, create_autospec, patch
from uuid import uuid4

import pytest
from redis import Redis
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_auth_sessions import cache as cache
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.dto import IssuedSession, VerifiedGoogleIdentity
from app.modules.auth.application.google_login import GoogleLoginService
from app.modules.auth.application.ports import GoogleIdentityRepository, SessionCache
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.errors import (
    AccountLinkingRequired,
    InvalidExternalIdentity,
    InvalidSession,
)
from app.modules.auth.infrastructure.orm import (
    CredentialModel,
    IdentityModel,
    OneTimeTokenModel,
    SessionModel,
)
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyGoogleIdentityRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.session_cache import RedisSessionCache
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.application.ports import (
    EmailAlreadyExists,
    EmailVerifier,
    UserAuthentication,
    UserRegistration,
)
from app.modules.users.infrastructure.orm import UserModel
from app.modules.users.infrastructure.repository import (
    SqlAlchemyEmailVerifier,
    SqlAlchemyUserAuthentication,
    SqlAlchemyUserRegistration,
)

NOW = datetime.now(UTC)
IDENTITY = VerifiedGoogleIdentity("google-subject", "student@example.com")


def service(database: Session, cache: SessionCache, settings: Settings) -> GoogleLoginService:
    return GoogleLoginService(
        SqlAlchemyUserRegistration(database),
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyEmailVerifier(database),
        SqlAlchemyGoogleIdentityRepository(database),
        SessionService(
            SqlAlchemySessionRepository(database),
            cache,
            settings,
            generate_token=generate_token,
            hash_token=hash_token,
        ),
        now=lambda: NOW,
    )


@pytest.mark.parametrize("path", ["linked", "new", "concurrent", "collision", "disabled"])
def test_resolution_policy(path: str) -> None:
    users = create_autospec(UserRegistration, instance=True)
    authentication = create_autospec(UserAuthentication, instance=True)
    verifier = create_autospec(EmailVerifier, instance=True)
    identities = create_autospec(GoogleIdentityRepository, instance=True)
    sessions = create_autospec(SessionService, instance=True)
    user_id = uuid4()
    users.create.return_value = user_id
    authentication.lock_active.return_value = path != "disabled"
    verifier.mark_verified.return_value = True
    identities.get_user_id.side_effect = {
        "linked": [user_id],
        "new": [None],
        "concurrent": [None, user_id],
        "collision": [None, None],
        "disabled": [user_id],
    }[path]
    if path in {"concurrent", "collision"}:
        users.create.side_effect = EmailAlreadyExists("private details")
    login = GoogleLoginService(
        users, authentication, verifier, identities, sessions, now=lambda: NOW
    )
    if path in {"collision", "disabled"}:
        error = AccountLinkingRequired if path == "collision" else InvalidExternalIdentity
        with pytest.raises(error) as caught:
            login.login(IDENTITY)
        assert "private" not in str(caught.value)
        sessions.create.assert_not_called()
    else:
        assert login.login(IDENTITY, user_agent="browser") is sessions.create.return_value
        sessions.create.assert_called_once_with(user_id, user_agent="browser", ip_address=None)
    if path == "new":
        users.create.assert_called_once_with(IDENTITY.email)
        verifier.mark_verified.assert_called_once_with(user_id, NOW)
        identities.create.assert_called_once_with(user_id, IDENTITY.subject, IDENTITY.email, NOW)
    else:
        verifier.mark_verified.assert_not_called()
        identities.create.assert_not_called()
    if path in {"linked", "disabled"}:
        users.create.assert_not_called()


def test_live_new_account_and_normal_session(
    concurrent_engine: Engine, cache: Mock, settings: Settings
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        issued = service(database, cache, settings).login(
            VerifiedGoogleIdentity(IDENTITY.subject, " Student@Example.COM "),
            user_agent="google-login-test",
            ip_address=ip_address("192.0.2.10"),
        )
        cache.set.assert_not_called()
    with Session(concurrent_engine) as database, database.begin():
        user = database.get(UserModel, issued.session.user_id)
        identity = database.scalar(select(IdentityModel))
        stored = database.get(SessionModel, issued.session.id)
        assert user and user.email == IDENTITY.email and user.email_verified_at == NOW
        assert identity and identity.user_id == user.id and identity.provider == "google"
        assert (
            identity.provider_subject == IDENTITY.subject and identity.provider_email == user.email
        )
        assert stored and stored.token_hash == hash_token(issued.token)
        assert stored.user_agent == "google-login-test" and str(stored.ip_address) == "192.0.2.10"
        assert issued.token not in repr(issued)
        assert database.scalar(select(func.count()).select_from(CredentialModel)) == 0
        assert database.scalar(select(func.count()).select_from(OneTimeTokenModel)) == 0
        assert service(database, cache, settings).sessions.validate(issued.token) == issued.session


@pytest.mark.parametrize("failure", ["email", "verification"])
def test_invalid_new_account_stops_before_identity_or_session(failure: str) -> None:
    users = create_autospec(UserRegistration, instance=True)
    authentication = create_autospec(UserAuthentication, instance=True)
    verifier = create_autospec(EmailVerifier, instance=True)
    identities = create_autospec(GoogleIdentityRepository, instance=True)
    sessions = create_autospec(SessionService, instance=True)
    identities.get_user_id.return_value = None
    verifier.mark_verified.return_value = False
    login = GoogleLoginService(users, authentication, verifier, identities, sessions)
    identity = VerifiedGoogleIdentity(
        IDENTITY.subject, "bad email" if failure == "email" else IDENTITY.email
    )
    with pytest.raises(InvalidExternalIdentity):
        login.login(identity)
    if failure == "email":
        users.create.assert_not_called()
        verifier.mark_verified.assert_not_called()
    identities.create.assert_not_called()
    authentication.lock_active.assert_not_called()
    sessions.create.assert_not_called()


@pytest.mark.parametrize("status", ["active", "disabled"])
def test_live_linked_subject_preserves_canonical_account(
    concurrent_engine: Engine, cache: Mock, settings: Settings, status: str
) -> None:
    user_id = uuid4()
    with Session(concurrent_engine) as database, database.begin():
        database.add(UserModel(id=user_id, email="original@example.com", status=status))
        database.flush()
        database.add(CredentialModel(user_id=user_id, password_hash="untouched-hash"))
        SqlAlchemyGoogleIdentityRepository(database).create(
            user_id, IDENTITY.subject, "old-provider@example.com", NOW
        )
    with Session(concurrent_engine) as database:
        if status == "disabled":
            with pytest.raises(InvalidExternalIdentity), database.begin():
                service(database, cache, settings).login(IDENTITY)
        else:
            with database.begin():
                issued = service(database, cache, settings).login(IDENTITY)
                assert issued.session.user_id == user_id
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, user_id)
        credential = database.get(CredentialModel, user_id)
        identity = database.scalar(select(IdentityModel))
        assert user and user.email == "original@example.com" and user.email_verified_at is None
        assert credential and credential.password_hash == "untouched-hash"
        assert identity and identity.provider_email == "old-provider@example.com"
        assert database.scalar(select(func.count()).select_from(UserModel)) == 1
        assert database.scalar(select(func.count()).select_from(SessionModel)) == (
            status == "active"
        )


@pytest.mark.parametrize("account", ["password", "google", "disabled"])
def test_live_email_collision_requires_linking(
    concurrent_engine: Engine, cache: Mock, settings: Settings, account: str
) -> None:
    user_id = uuid4()
    with Session(concurrent_engine) as database, database.begin():
        database.add(
            UserModel(
                id=user_id,
                email="Student@Example.com",
                email_verified_at=NOW,
                status="disabled" if account == "disabled" else "active",
            )
        )
        database.flush()
        if account != "google":
            database.add(CredentialModel(user_id=user_id, password_hash="untouched-hash"))
        else:
            SqlAlchemyGoogleIdentityRepository(database).create(
                user_id, "other-subject", IDENTITY.email, NOW
            )
    with Session(concurrent_engine) as database:
        with pytest.raises(AccountLinkingRequired), database.begin():
            service(database, cache, settings).login(IDENTITY)
    with Session(concurrent_engine) as database:
        user = database.get(UserModel, user_id)
        assert user and user.email == "Student@Example.com" and user.email_verified_at == NOW
        assert database.scalar(select(func.count()).select_from(UserModel)) == 1
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == (
            account == "google"
        )
        assert database.scalar(select(func.count()).select_from(SessionModel)) == 0
        if account != "google":
            credential = database.get(CredentialModel, user_id)
            assert credential and credential.password_hash == "untouched-hash"
    cache.set.assert_not_called()


@pytest.mark.parametrize("failure", ["verification", "identity", "session"])
def test_live_late_failure_rolls_back_all_records_and_allows_retry(
    concurrent_engine: Engine, cache: Mock, settings: Settings, failure: str
) -> None:
    with Session(concurrent_engine) as database:
        login = service(database, cache, settings)
        target, method = {
            "verification": (login.verifier, "mark_verified"),
            "identity": (login.identities, "create"),
            "session": (login.sessions.repository, "create"),
        }[failure]
        original = getattr(target, method)

        def fail_after_write(*args: object) -> None:
            original(*args)
            raise RuntimeError("injected failure")

        with patch.object(target, method, side_effect=fail_after_write):
            with pytest.raises(RuntimeError, match="injected failure"), database.begin():
                login.login(IDENTITY)
    with Session(concurrent_engine) as database, database.begin():
        for model in (UserModel, IdentityModel, SessionModel):
            assert database.scalar(select(func.count()).select_from(model)) == 0
        assert service(database, cache, settings).login(IDENTITY).session.user_id
    cache.set.assert_not_called()


@pytest.mark.parametrize("race", ["same", "email", "subject"])
def test_live_concurrent_creation_never_merges_or_leaves_partial_users(
    concurrent_engine: Engine, cache: Mock, settings: Settings, race: str
) -> None:
    barrier = Barrier(2)
    second = VerifiedGoogleIdentity(
        "different-subject" if race == "email" else IDENTITY.subject,
        "different@example.com" if race == "subject" else IDENTITY.email,
    )

    def attempt(identity: VerifiedGoogleIdentity) -> IssuedSession | Exception:
        with Session(concurrent_engine) as database:
            login = service(database, cache, settings)
            lookup = login.identities.get_user_id
            first = True

            def synchronized_lookup(subject: str):
                nonlocal first
                result = lookup(subject)
                if first:
                    first = False
                    assert result is None
                    barrier.wait(timeout=5)
                return result

            with patch.object(login.identities, "get_user_id", side_effect=synchronized_lookup):
                try:
                    with database.begin():
                        return login.login(identity)
                except (AccountLinkingRequired, InvalidExternalIdentity) as error:
                    return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt, identity) for identity in (IDENTITY, second)]
        results = [future.result(timeout=10) for future in futures]
    issued = [result for result in results if isinstance(result, IssuedSession)]
    assert len(issued) == (2 if race == "same" else 1)
    if race != "same":
        expected = AccountLinkingRequired if race == "email" else InvalidExternalIdentity
        assert sum(isinstance(result, expected) for result in results) == 1
    with Session(concurrent_engine) as database:
        assert database.scalar(select(func.count()).select_from(UserModel)) == 1
        assert database.scalar(select(func.count()).select_from(IdentityModel)) == 1
        assert database.scalar(select(func.count()).select_from(SessionModel)) == len(issued)
        assert len({result.session.user_id for result in issued}) == 1
        for identity in (IDENTITY, second):
            if race != "email":
                with database.begin_nested():
                    assert (
                        service(database, cache, settings).login(identity).session.user_id
                        == issued[0].session.user_id
                    )
                database.rollback()


def test_live_login_holds_active_user_lock_until_commit(
    concurrent_engine: Engine, cache: Mock, settings: Settings
) -> None:
    with Session(concurrent_engine) as database, database.begin():
        issued = service(database, cache, settings).login(IDENTITY)
    with Session(concurrent_engine) as login_database, login_database.begin():
        service(login_database, cache, settings).login(IDENTITY)
        with Session(concurrent_engine) as contender:
            with pytest.raises(OperationalError), contender.begin():
                contender.execute(text("SET LOCAL lock_timeout = '100ms'"))
                contender.execute(
                    update(UserModel)
                    .where(UserModel.id == issued.session.user_id)
                    .values(status="disabled")
                )


def test_live_google_session_uses_existing_redis_validation_and_revocation(
    concurrent_engine: Engine, settings: Settings
) -> None:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run Redis integration checks.")
    client = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    cache = RedisSessionCache(client)
    token_hash = None
    try:
        with Session(concurrent_engine) as database, database.begin():
            issued = service(database, cache, settings).login(IDENTITY)
            token_hash = issued.session.token_hash
            assert cache.get(token_hash) is None
        with Session(concurrent_engine) as database, database.begin():
            sessions = service(database, cache, settings).sessions
            assert sessions.validate(issued.token) == issued.session
            assert cache.get(token_hash) == issued.session
            sessions.revoke(issued.session.id)
        assert cache.get(token_hash) is None
        with Session(concurrent_engine) as database, database.begin():
            with pytest.raises(InvalidSession):
                service(database, cache, settings).sessions.validate(issued.token)
    finally:
        if token_hash is not None:
            cache.delete(token_hash)
        client.close()
