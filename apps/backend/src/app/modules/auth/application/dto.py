from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from app.modules.auth.domain.entities import AuthSession


@dataclass(frozen=True)
class IssuedSession:
    session: AuthSession
    token: str = field(repr=False)


@dataclass(frozen=True)
class RegistrationResult:
    user_id: UUID
    email: str
    session: IssuedSession
    verification_token: str = field(repr=False)


@dataclass(frozen=True)
class PasswordResetDelivery:
    """Internal delivery data; commit before sending, never return it from HTTP."""

    user_id: UUID
    email: str
    expires_at: datetime
    token: str = field(repr=False)


@dataclass(frozen=True)
class EmailVerificationDelivery:
    """Internal delivery data; commit before sending, never return it from HTTP."""

    user_id: UUID
    email: str
    expires_at: datetime
    token: str = field(repr=False)


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    """A signature- and claim-validated Google identity, without provider tokens."""

    subject: str
    email: str


type OAuthToken = Annotated[
    str, Field(strict=True, min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")
]


@dataclass(frozen=True)
class OAuthStateRecord:
    """Temporary internal state; nonce/verifier are needed for provider validation."""

    nonce: OAuthToken = field(repr=False)
    code_verifier: OAuthToken = field(repr=False)
    browser_token_hash: Annotated[
        str, Field(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")
    ] = field(repr=False)


@dataclass(frozen=True)
class OAuthStateStart:
    """Internal initiation data; set browser_token in an HttpOnly cookie before redirecting."""

    state: str = field(repr=False)
    nonce: str = field(repr=False)
    code_challenge: str = field(repr=False)
    browser_token: str = field(repr=False)


@dataclass(frozen=True)
class GoogleAuthorization:
    url: str = field(repr=False)
    browser_token: str = field(repr=False)
