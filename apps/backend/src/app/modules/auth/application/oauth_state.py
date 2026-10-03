import re
from base64 import urlsafe_b64encode
from collections.abc import Callable
from hashlib import sha256

from app.core.config import Settings
from app.modules.auth.application.dto import OAuthLinkContext, OAuthStateRecord, OAuthStateStart
from app.modules.auth.application.ports import OAuthStateStore
from app.modules.auth.domain.errors import InvalidOAuthState


class OAuthStateService:
    """Consume browser-bound state before any provider exchange or account mutation."""

    def __init__(
        self,
        store: OAuthStateStore,
        settings: Settings,
        *,
        generate_token: Callable[[], str],
        hash_token: Callable[[str], str],
    ) -> None:
        self.store = store
        self.ttl_seconds = settings.auth_oauth_state_ttl_seconds
        self.generate_token = generate_token
        self.hash_token = hash_token

    def start(self, link: OAuthLinkContext | None = None) -> OAuthStateStart:
        state, nonce, verifier, browser_token = (self.generate_token() for _ in range(4))
        record = OAuthStateRecord(nonce, verifier, self.hash_token(browser_token), link)
        self.store.create(self.hash_token(state), record, self.ttl_seconds)
        challenge = (
            urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
        )
        return OAuthStateStart(state, nonce, challenge, browser_token)

    def consume(self, state: str | None, browser_token: str | None) -> OAuthStateRecord:
        if (
            state is None
            or browser_token is None
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", state) is None
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", browser_token) is None
        ):
            raise InvalidOAuthState("Invalid or expired OAuth state.")
        record = self.store.consume(self.hash_token(state), self.hash_token(browser_token))
        if record is None:
            raise InvalidOAuthState("Invalid or expired OAuth state.")
        return record
