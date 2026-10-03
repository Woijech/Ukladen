import json
import re
from collections.abc import Callable
from hmac import compare_digest
from threading import RLock
from time import monotonic
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from app.core.config import Settings
from app.modules.auth.application.dto import VerifiedGoogleIdentity
from app.modules.auth.application.ports import ExternalIdentityUnavailable
from app.modules.auth.application.registration import normalize_email
from app.modules.auth.domain.errors import InvalidExternalIdentity, InvalidRegistration

DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class GoogleOidcProvider:
    """Caller owns the HTTP client and must consume browser-bound OAuth state before callback."""

    def __init__(
        self, settings: Settings, client: httpx.Client, *, clock: Callable[[], float] = monotonic
    ) -> None:
        if (
            settings.google_client_id is None
            or settings.google_client_secret is None
            or settings.google_redirect_uri is None
        ):
            raise ExternalIdentityUnavailable("External identity provider is unavailable.")
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = str(settings.google_redirect_uri)
        self.client = client
        self.clock = clock
        self._documents: dict[str, tuple[float, dict[str, Any]]] = {}
        # ponytail: cache fills share one lock; split locks if provider latency limits throughput.
        self._lock = RLock()

    @staticmethod
    def _check_token(value: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None:
            raise InvalidExternalIdentity("Invalid external identity.")

    def _request_json(
        self, method: str, url: str, *, data: dict[str, str] | None = None
    ) -> tuple[dict[str, Any], int]:
        try:
            with self.client.stream(
                method, url, data=data, timeout=3, follow_redirects=False
            ) as response:
                if method == "POST" and response.status_code in (400, 401):
                    raise InvalidExternalIdentity("Invalid external identity.")
                if response.status_code != 200:
                    raise ExternalIdentityUnavailable("External identity provider is unavailable.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ValueError("Provider response is too large.")
                document = json.loads(body)
                if not isinstance(document, dict):
                    raise ValueError("Invalid provider response.")
                cache_control = response.headers.get("cache-control", "").lower()
                match = re.search(r"(?:^|,)\s*max-age\s*=\s*(\d+)\s*(?:,|$)", cache_control)
                age = int(response.headers.get("age", "0"))
                ttl = max(0, min(3600, int(match[1]) - max(0, age))) if match else 0
                if "no-store" in cache_control or "no-cache" in cache_control:
                    ttl = 0
                return document, ttl
        except httpx.HTTPError, ValueError, TypeError, OverflowError:
            raise ExternalIdentityUnavailable(
                "External identity provider is unavailable."
            ) from None

    def _document(self, url: str, *, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            cached = self._documents.get(url)
            if not refresh and cached is not None and self.clock() < cached[0]:
                return cached[1]
            document, ttl = self._request_json("GET", url)
            if ttl > 0:
                self._documents[url] = (self.clock() + ttl, document)
            else:
                self._documents.pop(url, None)
            return document

    def _discovery(self) -> dict[str, Any]:
        document = self._document(DISCOVERY_URL)
        algorithms = document.get("id_token_signing_alg_values_supported")
        challenges = document.get("code_challenge_methods_supported")
        if (
            document.get("issuer") != ISSUERS[0]
            or not isinstance(algorithms, list)
            or "RS256" not in algorithms
            or not isinstance(challenges, list)
            or "S256" not in challenges
        ):
            raise ExternalIdentityUnavailable("External identity provider is unavailable.")
        hosts = {
            "authorization_endpoint": "accounts.google.com",
            "token_endpoint": "oauth2.googleapis.com",
            "jwks_uri": "www.googleapis.com",
        }
        for field, host in hosts.items():
            value = document.get(field)
            if not isinstance(value, str):
                raise ExternalIdentityUnavailable("External identity provider is unavailable.")
            try:
                parsed = urlsplit(value)
                valid = (
                    parsed.scheme == "https"
                    and parsed.netloc == host
                    and parsed.path.startswith("/")
                    and not parsed.query
                    and not parsed.fragment
                    and not any(character.isspace() for character in value)
                )
            except ValueError:
                valid = False
            if not valid:
                raise ExternalIdentityUnavailable("External identity provider is unavailable.")
        return document

    def build_authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        for value in (state, nonce, code_challenge):
            self._check_token(value)
        document = self._discovery()
        return (
            document["authorization_endpoint"]
            + "?"
            + urlencode(
                {
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "response_type": "code",
                    "scope": "openid email",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    def _signing_key(self, url: str, kid: str) -> RSAPublicKey:
        for refresh in (False, True):
            document = self._document(url, refresh=refresh)
            keys = document.get("keys")
            if not isinstance(keys, list) or not all(isinstance(key, dict) for key in keys):
                raise ExternalIdentityUnavailable("External identity provider is unavailable.")
            matches = [key for key in keys if key.get("kid") == kid]
            if not matches:
                continue
            if len(matches) != 1:
                raise InvalidExternalIdentity("Invalid external identity.")
            key = matches[0]
            if (
                key.get("kty") != "RSA"
                or key.get("use", "sig") != "sig"
                or key.get("alg", "RS256") != "RS256"
                or ("key_ops" in key and key["key_ops"] != ["verify"])
                or "d" in key
            ):
                raise InvalidExternalIdentity("Invalid external identity.")
            try:
                public = jwt.PyJWK.from_dict(key, algorithm="RS256").key
            except jwt.PyJWTError, ValueError, TypeError:
                raise ExternalIdentityUnavailable(
                    "External identity provider is unavailable."
                ) from None
            if not isinstance(public, RSAPublicKey) or public.key_size < 2048:
                raise InvalidExternalIdentity("Invalid external identity.")
            return public
        raise InvalidExternalIdentity("Invalid external identity.")

    def resolve_callback(
        self, *, code: str, code_verifier: str, nonce: str
    ) -> VerifiedGoogleIdentity:
        self._check_token(nonce)
        if (
            not 1 <= len(code) <= 4096
            or re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", code_verifier) is None
        ):
            raise InvalidExternalIdentity("Invalid external identity.")
        document = self._discovery()
        result, _ = self._request_json(
            "POST",
            document["token_endpoint"],
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret.get_secret_value(),
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        token = result.get("id_token")
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise InvalidExternalIdentity("Invalid external identity.")
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256"
                or "crit" in header
                or not isinstance(kid, str)
                or not 1 <= len(kid) <= 256
            ):
                raise InvalidExternalIdentity("Invalid external identity.")
            claims = jwt.decode(
                token,
                self._signing_key(document["jwks_uri"], kid),
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=ISSUERS,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "exp",
                        "iat",
                        "nonce",
                        "email",
                        "email_verified",
                    ],
                    "strict_aud": True,
                },
            )
            subject, email, received_nonce = claims["sub"], claims["email"], claims["nonce"]
            if (
                not isinstance(subject, str)
                or not 1 <= len(subject) <= 255
                or not subject.isascii()
                or any(character.isspace() or ord(character) < 32 for character in subject)
                or not isinstance(email, str)
                or claims["email_verified"] is not True
                or not isinstance(received_nonce, str)
                or not received_nonce.isascii()
                or not compare_digest(received_nonce, nonce)
                or claims.get("azp", self.client_id) != self.client_id
                or type(claims["iat"]) is not int
                or type(claims["exp"]) is not int
                or not 0 <= claims["iat"] < claims["exp"]
            ):
                raise InvalidExternalIdentity("Invalid external identity.")
            return VerifiedGoogleIdentity(subject=subject, email=normalize_email(email))
        except jwt.PyJWTError, InvalidRegistration, ValueError, TypeError, KeyError:
            raise InvalidExternalIdentity("Invalid external identity.") from None
