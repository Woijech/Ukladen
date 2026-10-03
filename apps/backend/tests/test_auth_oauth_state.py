import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import monotonic, sleep
from unittest.mock import Mock, create_autospec, patch

import pytest
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from test_auth_sessions import settings as settings

from app.core.config import Settings
from app.modules.auth.application.dto import OAuthStateRecord
from app.modules.auth.application.oauth_state import OAuthStateService
from app.modules.auth.application.ports import OAuthStateStore, OAuthStateUnavailable
from app.modules.auth.domain.errors import InvalidOAuthState
from app.modules.auth.infrastructure.oauth_state import RedisOAuthStateStore
from app.modules.auth.infrastructure.token_service import generate_token, hash_token


def service(store: OAuthStateStore, settings: Settings) -> OAuthStateService:
    return OAuthStateService(store, settings, generate_token=generate_token, hash_token=hash_token)


def test_start_hashes_binding_and_uses_s256_pkce(settings: Settings) -> None:
    store = create_autospec(OAuthStateStore, instance=True)
    tokens = [
        generate_token(),
        generate_token(),
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        generate_token(),
    ]
    configured = settings.model_copy(update={"auth_oauth_state_ttl_seconds": 23})
    started = OAuthStateService(
        store, configured, generate_token=Mock(side_effect=tokens), hash_token=hash_token
    ).start()
    assert started.state == tokens[0] and started.nonce == tokens[1]
    assert started.browser_token == tokens[3]
    assert started.code_challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    record = OAuthStateRecord(tokens[1], tokens[2], hash_token(tokens[3]))
    store.create.assert_called_once_with(hash_token(tokens[0]), record, 23)
    assert all(token not in repr(started) + repr(record) for token in tokens)
    store.consume.return_value = record
    assert service(store, settings).consume(started.state, started.browser_token) == record
    store.consume.assert_called_once_with(hash_token(tokens[0]), hash_token(tokens[3]))


@pytest.mark.parametrize("field", ["state", "browser"])
@pytest.mark.parametrize(
    "token", [None, "", "x" * 42, "x" * 44, "!" * 43, "é" * 43, "x" * 42 + "\n"]
)
def test_bad_callback_tokens_are_rejected_before_io(
    settings: Settings, field: str, token: str | None
) -> None:
    store = create_autospec(OAuthStateStore, instance=True)
    with pytest.raises(InvalidOAuthState, match="Invalid or expired OAuth state"):
        service(store, settings).consume(
            token if field == "state" else generate_token(),
            token if field == "browser" else generate_token(),
        )
    store.consume.assert_not_called()


def test_missing_or_consumed_state_has_fixed_error(settings: Settings) -> None:
    store = create_autospec(OAuthStateStore, instance=True)
    store.consume.return_value = None
    with pytest.raises(InvalidOAuthState, match=r"^Invalid or expired OAuth state\.$"):
        service(store, settings).consume(generate_token(), generate_token())


@pytest.mark.parametrize("ttl", [0, -1])
def test_state_expiry_setting_must_be_positive(settings: Settings, ttl: int) -> None:
    assert Settings.model_fields["auth_oauth_state_ttl_seconds"].default == 600
    with pytest.raises(ValidationError):
        Settings.model_validate(settings.model_dump() | {"auth_oauth_state_ttl_seconds": ttl})


def test_redis_payload_and_wrong_browser_cannot_consume(settings: Settings) -> None:
    client = create_autospec(Redis, instance=True)
    client.set.return_value = True
    store = RedisOAuthStateStore(client)
    started = service(store, settings).start()
    key, payload = client.set.call_args.args
    assert key == f"ukladen:auth:oauth:{hash_token(started.state)}"
    assert client.set.call_args.kwargs == {"ex": 600, "nx": True}
    assert started.state.encode() not in payload and started.browser_token.encode() not in payload
    assert json.loads(payload)["browser_token_hash"] == hash_token(started.browser_token)
    client.get.return_value = payload
    with pytest.raises(InvalidOAuthState):
        service(store, settings).consume(started.state, generate_token())
    client.eval.assert_not_called()
    client.eval.return_value = 1
    record = service(store, settings).consume(started.state, started.browser_token)
    assert record.nonce == started.nonce
    assert client.eval.call_args.args[1:] == (1, key, payload.decode())


@pytest.mark.parametrize(
    "mutation", ["json", "missing", "nonce", "verifier", "hash", "type", "oversize"]
)
def test_malformed_redis_records_fail_closed(settings: Settings, mutation: str) -> None:
    client = create_autospec(Redis, instance=True)
    payload = {
        "nonce": generate_token(),
        "code_verifier": generate_token(),
        "browser_token_hash": hash_token(generate_token()),
    }
    if mutation == "missing":
        del payload["nonce"]
    elif mutation == "nonce":
        payload["nonce"] = "é" * 43
    elif mutation == "verifier":
        payload["code_verifier"] = "x" * 42 + "\n"
    elif mutation == "hash":
        payload["browser_token_hash"] = "z" * 64
    value: str | int = json.dumps(payload)
    if mutation == "json":
        value = "invalid-json-private-token"
    elif mutation == "type":
        value = 12
    elif mutation == "oversize":
        value = "x" * 1025
    client.get.return_value = value
    with pytest.raises(InvalidOAuthState) as error:
        service(RedisOAuthStateStore(client), settings).consume(generate_token(), generate_token())
    assert str(error.value) == "Invalid or expired OAuth state."
    assert "private-token" not in str(error.value)
    client.eval.assert_not_called()


@pytest.mark.parametrize("operation", ["set", "get", "eval"])
def test_redis_outages_are_sanitized(settings: Settings, operation: str) -> None:
    client = create_autospec(Redis, instance=True)
    client.set.return_value = True
    login = service(RedisOAuthStateStore(client), settings)
    if operation == "set":
        client.set.side_effect = RedisConnectionError("private token and Redis credentials")
        action = login.start
    else:
        started = login.start()
        client.get.return_value = client.set.call_args.args[1]
        getattr(client, operation).side_effect = RedisConnectionError(
            "private token and Redis credentials"
        )

        def action() -> object:
            return login.consume(started.state, started.browser_token)

    with pytest.raises(OAuthStateUnavailable) as error:
        action()
    assert str(error.value) == "OAuth state is unavailable."
    assert error.value.__suppress_context__


@pytest.mark.parametrize("result", [None, False])
def test_creation_failure_never_returns_initiation(settings: Settings, result: bool | None) -> None:
    client = create_autospec(Redis, instance=True)
    client.set.return_value = result
    with pytest.raises(OAuthStateUnavailable):
        service(RedisOAuthStateStore(client), settings).start()


@pytest.mark.parametrize("result", [0, None, "1", 2])
def test_consume_requires_successful_atomic_delete(
    settings: Settings, result: int | str | None
) -> None:
    client = create_autospec(Redis, instance=True)
    client.set.return_value = True
    login = service(RedisOAuthStateStore(client), settings)
    started = login.start()
    client.get.return_value = client.set.call_args.args[1]
    client.eval.return_value = result
    expected = InvalidOAuthState if result == 0 else OAuthStateUnavailable
    with pytest.raises(expected):
        login.consume(started.state, started.browser_token)


@pytest.fixture
def live_redis() -> Iterator[Redis]:
    url = os.environ.get("AUTH_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set AUTH_TEST_REDIS_URL to run Redis OAuth state integration checks.")
    client = Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
    try:
        yield client
    finally:
        client.close()


def test_live_browser_binding_and_single_use(live_redis: Redis, settings: Settings) -> None:
    store = RedisOAuthStateStore(live_redis)
    login = service(store, settings)
    started = login.start()
    key = f"ukladen:auth:oauth:{hash_token(started.state)}"
    try:
        ttl = live_redis.ttl(key)
        assert isinstance(ttl, int) and 0 < ttl <= 600
        with pytest.raises(InvalidOAuthState):
            login.consume(started.state, generate_token())
        assert live_redis.exists(key)
        record = login.consume(started.state, started.browser_token)
        assert record.nonce == started.nonce and not live_redis.exists(key)
        with pytest.raises(InvalidOAuthState):
            login.consume(started.state, started.browser_token)
    finally:
        live_redis.delete(key)


def test_live_expiry_and_creation_collision(live_redis: Redis, settings: Settings) -> None:
    store = RedisOAuthStateStore(live_redis)
    login = service(store, settings)
    started = login.start()
    state_hash = hash_token(started.state)
    key = f"ukladen:auth:oauth:{state_hash}"
    try:
        original = live_redis.get(key)
        with pytest.raises(OAuthStateUnavailable):
            store.create(
                state_hash,
                OAuthStateRecord(generate_token(), generate_token(), hash_token(generate_token())),
                60,
            )
        assert live_redis.get(key) == original
        live_redis.pexpire(key, 1)
        deadline = monotonic() + 2
        while live_redis.exists(key) and monotonic() < deadline:
            sleep(0.005)
        assert not live_redis.exists(key)
        with pytest.raises(InvalidOAuthState):
            login.consume(started.state, started.browser_token)
    finally:
        live_redis.delete(key)


@pytest.mark.parametrize("race", ["callbacks", "expiry", "replacement"])
def test_live_atomic_consumption_races(live_redis: Redis, settings: Settings, race: str) -> None:
    store = RedisOAuthStateStore(live_redis)
    login = service(store, settings)
    started = login.start()
    key = f"ukladen:auth:oauth:{hash_token(started.state)}"
    try:
        if race == "callbacks":
            barrier = Barrier(2)
            read = live_redis.get

            def synchronized_get(key: str):
                result = read(key)
                barrier.wait(timeout=5)
                return result

            def callback() -> OAuthStateRecord | None:
                try:
                    return login.consume(started.state, started.browser_token)
                except InvalidOAuthState:
                    return None

            with patch.object(live_redis, "get", side_effect=synchronized_get):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(callback) for _ in range(2)]
                    results = [future.result(timeout=10) for future in futures]
            assert sum(result is not None for result in results) == 1
            assert not live_redis.exists(key)
        else:
            consume = live_redis.eval
            replacement = store.adapter.dump_json(
                OAuthStateRecord(
                    generate_token(), generate_token(), hash_token(started.browser_token)
                )
            )

            def change_before_delete(script: str, numkeys: int, *args: str):
                if race == "expiry":
                    live_redis.pexpire(key, 1)
                    sleep(0.02)
                else:
                    live_redis.set(key, replacement, ex=60)
                return consume(script, numkeys, *args)

            with patch.object(live_redis, "eval", side_effect=change_before_delete):
                with pytest.raises(InvalidOAuthState):
                    login.consume(started.state, started.browser_token)
            if race == "replacement":
                assert live_redis.get(key) == replacement
    finally:
        live_redis.delete(key)
