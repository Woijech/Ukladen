from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class GoogleCallbackRequest(BaseModel):
    state: SecretStr | None = Field(default=None, min_length=43, max_length=43, repr=False)
    code: SecretStr | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    error: SecretStr | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class GoogleLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr = Field(min_length=1, max_length=1024, repr=False)
    new_password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class EmailVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=43, max_length=43, repr=False)


class EmailVerificationResendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailVerificationRequestResponse(BaseModel):
    detail: Literal["Email verification request accepted."] = "Email verification request accepted."


class PasswordResetConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=43, max_length=43, repr=False)
    new_password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)


class PasswordResetRequestResponse(BaseModel):
    detail: Literal["Password reset request accepted."] = "Password reset request accepted."


class LoginResponse(BaseModel):
    user_id: UUID
    session_id: UUID
    expires_at: datetime


class CsrfResponse(BaseModel):
    csrf_token: str = Field(repr=False)


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: IPv4Address | IPv6Address | None
    is_current: bool
