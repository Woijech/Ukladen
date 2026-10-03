from app.modules.auth.application.dto import GoogleAuthorization, VerifiedGoogleIdentity
from app.modules.auth.application.oauth_state import OAuthStateService
from app.modules.auth.application.ports import ExternalIdentityProvider
from app.modules.auth.domain.errors import InvalidExternalIdentity


class GoogleOAuthService:
    def __init__(self, states: OAuthStateService, provider: ExternalIdentityProvider) -> None:
        self.states = states
        self.provider = provider

    def start(self) -> GoogleAuthorization:
        started = self.states.start()
        # ponytail: failed starts leave expiring state; add deletion if this pressures Redis.
        url = self.provider.build_authorization_url(
            state=started.state, nonce=started.nonce, code_challenge=started.code_challenge
        )
        return GoogleAuthorization(url, started.browser_token)

    def resolve_callback(
        self,
        *,
        state: str | None,
        browser_token: str | None,
        code: str | None,
        error: str | None = None,
    ) -> VerifiedGoogleIdentity:
        record = self.states.consume(state, browser_token)
        if error is not None or code is None:
            raise InvalidExternalIdentity("Invalid external identity.")
        return self.provider.resolve_callback(
            code=code, code_verifier=record.code_verifier, nonce=record.nonce
        )
