from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast

from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.integrations.storage.s3 import create_s3_client, log_storage_failure
from app.modules.materials.domain.materials import MAX_FILE_BYTES, MaterialStorageUnavailable


class S3MaterialStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket, self.client = settings.s3_bucket, create_s3_client(settings)

    def put(self, key: str, body: BinaryIO, size: int, media_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentLength=size,
                ContentType=media_type,
                CacheControl="no-store",
            )
        except (BotoCoreError, ClientError, OSError) as error:
            log_storage_failure("material_put", error)
            raise MaterialStorageUnavailable() from None

    def get(self, key: str, size: int) -> BinaryIO | None:
        temporary = cast(BinaryIO, SpooledTemporaryFile(max_size=1024 * 1024))
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            body = result["Body"]
            try:
                if not 1 <= size <= MAX_FILE_BYTES or result["ContentLength"] != size:
                    raise MaterialStorageUnavailable()
                total = 0
                for chunk in body.iter_chunks(64 * 1024):
                    total += len(chunk)
                    if total > size:
                        raise MaterialStorageUnavailable()
                    temporary.write(chunk)
                if total != size:
                    raise MaterialStorageUnavailable()
            finally:
                body.close()
            temporary.seek(0)
            return temporary
        except ClientError as error:
            temporary.close()
            if error.response.get("Error", {}).get("Code") == "NoSuchKey":
                return None
            log_storage_failure("material_get", error)
            raise MaterialStorageUnavailable() from None
        except (BotoCoreError, OSError) as error:
            temporary.close()
            log_storage_failure("material_get", error)
            raise MaterialStorageUnavailable() from None
        except Exception:
            temporary.close()
            raise

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            log_storage_failure("material_delete", error)
            raise MaterialStorageUnavailable() from None

    def close(self) -> None:
        self.client.close()
