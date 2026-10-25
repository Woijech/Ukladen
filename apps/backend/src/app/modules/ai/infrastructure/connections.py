"""API-consumer-only deployment catalog and authenticated credential encryption."""

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.ai.application.connections import ModelOffering, ModelOption, require_key
from app.modules.ai.domain.connections import ConnectionUnavailable, PersonalConnection
from app.modules.ai.domain.state import AiNotFound


def read_file(path: Path, *, secret: bool = False) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or (secret and metadata.st_mode & 0o077):
                raise ValueError("Unsafe secret file permissions.")
            data = stream.read(65537)
            if len(data) > 65536:
                raise ValueError("AI configuration is too large.")
            return data
    except OSError, ValueError:
        raise ConnectionUnavailable("AI configuration or secret file is unavailable.") from None


class CatalogEntry(ModelOffering):
    enabled: bool = False
    listed: bool = False
    public: bool = False
    allowed_user_ids: tuple[UUID, ...] = Field(default=(), max_length=1000)
    operator_key_file: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]+\.key$")


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    entries: tuple[CatalogEntry, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def unique_entries(self):
        if len({entry.id for entry in self.entries}) != len(self.entries):
            raise ValueError("Duplicate model offering.")
        if sum(entry.is_default for entry in self.entries) > 1:
            raise ValueError("Only one default model offering is supported.")
        for entry in self.entries:
            if entry.model.startswith("openrouter/") or entry.model.endswith(
                (":online", ":batch", "-latest")
            ):
                raise ValueError("Choose a fixed text model, without routers or hosted tools.")
        return self


class FileConnectionConfiguration:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _entries(self) -> tuple[CatalogEntry, ...]:
        try:
            return Catalog.model_validate_json(read_file(self.path)).entries
        except ValueError:
            raise ConnectionUnavailable("AI catalog is invalid.") from None

    def _entry(self, offering_id: str) -> CatalogEntry:
        entry = next((entry for entry in self._entries() if entry.id == offering_id), None)
        if entry is None or not entry.enabled:
            raise AiNotFound()
        return entry

    @staticmethod
    def _public(entry: CatalogEntry) -> ModelOffering:
        return ModelOffering.model_validate(
            {name: getattr(entry, name) for name in ModelOffering.model_fields}
        )

    def offerings(self, user_id: UUID) -> list[ModelOffering]:
        return [
            self._public(entry)
            for entry in self._entries()
            if entry.enabled and (entry.public or user_id in entry.allowed_user_ids)
        ]

    def model_options(self, user_id: UUID) -> list[ModelOption]:
        options = []
        for entry in self._entries():
            if not (entry.enabled or entry.listed) or not (
                entry.public or user_id in entry.allowed_user_ids
            ):
                continue
            operator_available = False
            if entry.enabled:
                try:
                    self.operator_key(entry.id)
                    operator_available = True
                except ConnectionUnavailable:
                    pass
            options.append(
                ModelOption(
                    **self._public(entry).model_dump(),
                    available=entry.enabled,
                    operator_available=operator_available,
                )
            )
        return options

    def offering(self, user_id: UUID, offering_id: str) -> ModelOffering:
        entry = self._entry(offering_id)
        if not entry.public and user_id not in entry.allowed_user_ids:
            raise AiNotFound()
        return self._public(entry)

    def operator_key(self, offering_id: str) -> str:
        reference = self._entry(offering_id).operator_key_file
        if reference is None:
            raise ConnectionUnavailable("Operator connection is not configured.")
        try:
            return require_key(
                read_file(self.path.parent / reference, secret=True).decode().strip()
            )
        except ValueError:
            raise ConnectionUnavailable("Operator credential is invalid.") from None

    def quota_scope(self, offering_id: str) -> str:
        reference = self._entry(offering_id).operator_key_file
        # The same deployment secret shared by several offerings shares its request quota.
        digest = hashlib.sha256(f"{self.path.resolve()}:{reference}".encode()).hexdigest()
        return f"operator:{digest}"

    def _keyring(self) -> tuple[str, dict[str, bytes]]:
        try:
            data = json.loads(read_file(self.path.parent / "master-keys.json", secret=True))
            active, encoded = data["active"], data["keys"]
            if not isinstance(active, str) or not 1 <= len(encoded) <= 8:
                raise ValueError("Invalid encryption keyring.")
            keys = {}
            for identifier, value in encoded.items():
                if (
                    not isinstance(identifier, str)
                    or not identifier.isalnum()
                    or len(identifier) > 32
                ):
                    raise ValueError("Invalid encryption key identifier.")
                key = base64.b64decode(value, validate=True)
                if len(key) != 32:
                    raise ValueError("Encryption keys must contain 32 bytes.")
                keys[identifier] = key
            if active not in keys:
                raise ValueError("Active encryption key is missing.")
            return active, keys
        except ValueError, KeyError, TypeError, AttributeError:
            raise ConnectionUnavailable("Credential encryption is unavailable.") from None

    @staticmethod
    def _context(user_id: UUID, connection_id: UUID) -> bytes:
        return f"ukladen:openrouter:v1:{user_id}:{connection_id}".encode()

    def encrypt(self, user_id: UUID, connection_id: UUID, key: str) -> tuple[str, bytes]:
        active, keys = self._keyring()
        nonce = os.urandom(12)
        ciphertext = AESGCM(keys[active]).encrypt(
            nonce, require_key(key).encode(), self._context(user_id, connection_id)
        )
        return active, nonce + ciphertext

    def decrypt(self, connection: PersonalConnection) -> str:
        try:
            _, keys = self._keyring()
            ciphertext = connection.encrypted_key
            key_id = connection.encryption_key_id
            if ciphertext is None or key_id is None or connection.disconnected_at is not None:
                raise ValueError("Disconnected credential.")
            cleartext = AESGCM(keys[key_id]).decrypt(
                ciphertext[:12], ciphertext[12:], self._context(connection.user_id, connection.id)
            )
            return require_key(cleartext.decode())
        except Exception:
            raise ConnectionUnavailable("Credential cannot be decrypted.") from None
