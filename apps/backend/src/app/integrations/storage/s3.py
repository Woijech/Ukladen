import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.core.logging import log_failure
from app.modules.users.application.ports import AvatarStorageUnavailable
from app.modules.users.domain.avatar import MAX_AVATAR_BYTES

logger = logging.getLogger(__name__)


def log_storage_failure(operation: str, error: BaseException) -> None:
    code = error.response.get("Error", {}).get("Code") if isinstance(error, ClientError) else None
    if not isinstance(code, str) or code not in {
        "AccessDenied",
        "NoSuchBucket",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "SlowDown",
        "RequestTimeout",
        "ServiceUnavailable",
        "InternalError",
    }:
        code = "storage_error"
    log_failure(
        logger,
        "storage.operation_failed",
        error,
        dependency="s3",
        operation=operation,
        error_code=code,
    )


def create_s3_client(settings: Settings):
    return boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint),
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=3,
            retries={"mode": "standard", "total_max_attempts": 2},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


class S3AvatarStorage:
    """Private objects in the existing bucket; never log SDK error payloads or object keys."""

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = create_s3_client(settings)

    def put(self, key: str, content: bytes) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType="image/png",
                CacheControl="no-store",
            )
        except (BotoCoreError, ClientError) as error:
            log_storage_failure("put", error)
            raise AvatarStorageUnavailable() from None

    def get(self, key: str) -> bytes | None:
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            body = result["Body"]
            try:
                content = body.read(MAX_AVATAR_BYTES + 1)
            finally:
                body.close()
            if len(content) > MAX_AVATAR_BYTES or not content.startswith(b"\x89PNG\r\n\x1a\n"):
                logger.error("storage.invalid_avatar_object")
                raise AvatarStorageUnavailable()
            return content
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "NoSuchKey":
                return None
            log_storage_failure("get", error)
            raise AvatarStorageUnavailable() from None
        except (BotoCoreError, OSError) as error:
            log_storage_failure("get", error)
            raise AvatarStorageUnavailable() from None

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            log_storage_failure("delete", error)
            raise AvatarStorageUnavailable() from None

    def close(self) -> None:
        self.client.close()
