import os
from collections.abc import Iterator
from io import BytesIO
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import Stubber
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_auth_http import browser_login, csrf_headers, seed_user
from test_auth_http import browser_settings as browser_settings
from test_auth_http import live_client as live_client
from test_auth_login import password_hash as password_hash
from test_auth_sessions import concurrent_engine as concurrent_engine
from test_auth_sessions import settings as settings
from test_users_avatar import image_bytes

from app.core.config import Settings
from app.integrations.storage.s3 import S3AvatarStorage
from app.modules.users.application.ports import AvatarStorageUnavailable
from app.modules.users.infrastructure.orm import UserModel


def test_s3_adapter_signed_operations_and_safe_errors(settings: Settings) -> None:
    storage = S3AvatarStorage(settings)
    png = image_bytes()
    key = f"avatars/{uuid4()}/{uuid4().hex}.png"
    try:
        assert storage.client.meta.config.signature_version == "s3v4"
        assert storage.client.meta.config.s3["addressing_style"] == "path"
        with Stubber(storage.client) as stub:
            stub.add_response(
                "put_object",
                {},
                {
                    "Bucket": "test",
                    "Key": key,
                    "Body": png,
                    "ContentType": "image/png",
                    "CacheControl": "no-store",
                },
            )
            storage.put(key, png)
            body = StreamingBody(BytesIO(png), len(png))
            stub.add_response("get_object", {"Body": body}, {"Bucket": "test", "Key": key})
            assert storage.get(key) == png and body._raw_stream.closed
            stub.add_response("delete_object", {}, {"Bucket": "test", "Key": key})
            storage.delete(key)
            stub.add_client_error(
                "get_object",
                service_error_code="NoSuchKey",
                service_message="private-details",
                http_status_code=404,
            )
            assert storage.get(key) is None
            for operation in ("put_object", "get_object", "delete_object"):
                stub.add_client_error(
                    operation,
                    service_error_code="AccessDenied",
                    service_message="private-details",
                    http_status_code=403,
                )
            for operation in (
                lambda: storage.put(key, png),
                lambda: storage.get(key),
                lambda: storage.delete(key),
            ):
                with pytest.raises(AvatarStorageUnavailable) as error:
                    operation()
                assert "private" not in str(error.value)
            stub.assert_no_pending_responses()
    finally:
        storage.close()


def test_s3_adapter_transport_and_corrupt_object_fail_closed(settings: Settings) -> None:
    storage = S3AvatarStorage(settings)
    original = storage.client
    mock = Mock()
    storage.client = mock
    try:
        mock.put_object.side_effect = EndpointConnectionError(endpoint_url="http://private-storage")
        with pytest.raises(AvatarStorageUnavailable) as error:
            storage.put("key", b"png")
        assert "private" not in str(error.value)
        body = StreamingBody(BytesIO(b"not-png"), 7)
        mock.get_object.return_value = {"Body": body}
        with pytest.raises(AvatarStorageUnavailable):
            storage.get("key")
        assert body._raw_stream.closed
    finally:
        original.close()


@pytest.fixture
def live_avatar_storage(settings: Settings) -> Iterator[S3AvatarStorage]:
    endpoint = os.environ.get("AVATAR_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("Set AVATAR_TEST_S3_ENDPOINT and test bucket credentials for SeaweedFS checks.")
    config = Settings.model_validate(
        settings.model_dump()
        | {
            "s3_endpoint": endpoint,
            "s3_access_key": os.environ["AVATAR_TEST_S3_ACCESS_KEY"],
            "s3_secret_key": os.environ["AVATAR_TEST_S3_SECRET_KEY"],
            "s3_bucket": os.environ["AVATAR_TEST_S3_BUCKET"],
        }
    )
    storage = S3AvatarStorage(config)
    try:
        yield storage
    finally:
        storage.close()


def test_live_seaweedfs_avatar_round_trip(
    live_client: TestClient,
    live_avatar_storage: S3AvatarStorage,
    concurrent_engine: Engine,
    password_hash: str,
) -> None:
    # The bucket is supplied by the test service; only generated object keys are changed.
    storage = live_avatar_storage
    application = cast(FastAPI, live_client.app)
    application.state.avatar_storage.close()
    application.state.avatar_storage = storage
    seed_user(concurrent_engine, "student@example.com", password_hash)
    browser_login(live_client)
    headers = csrf_headers(live_client) | {"Content-Type": "image/png"}
    original_keys: list[str] = []
    try:
        for color in ("red", "blue"):
            response = live_client.put(
                "/api/v1/users/me/avatar", headers=headers, content=image_bytes(color=color)
            )
            assert (
                response.status_code == 200
                and response.json()["avatar_url"] == "/api/v1/users/me/avatar"
            )
            with Session(concurrent_engine) as database:
                key = database.scalar(select(UserModel.avatar_key))
                assert key
                original_keys.append(key)
            assert live_client.get("/api/v1/users/me/avatar").content == storage.get(key)
        assert storage.get(original_keys[0]) is None
        assert (
            live_client.delete(
                "/api/v1/users/me/avatar", headers=csrf_headers(live_client)
            ).status_code
            == 204
        )
        assert storage.get(original_keys[-1]) is None
        assert live_client.get("/api/v1/users/me/avatar").status_code == 404
    finally:
        for key in original_keys:
            storage.delete(key)
