from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024, repr=False)


class LoginResponse(BaseModel):
    user_id: UUID
    session_id: UUID
    expires_at: datetime


class CsrfResponse(BaseModel):
    csrf_token: str = Field(repr=False)
