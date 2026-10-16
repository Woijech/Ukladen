from ipaddress import IPv4Address, IPv6Address

from app.modules.auth.application.dto import (
    GoogleCallbackResult,
    GoogleEmailDelivery,
    IssuedSession,
)
from app.modules.auth.application.google_email_link import GoogleEmailLinkService
from app.modules.auth.application.google_link import GoogleLinkService
from app.modules.auth.application.google_login import GoogleLoginService
from app.modules.auth.domain.errors import AccountLinkingRequired


class GoogleSignInService:
    def __init__(
        self,
        accounts: GoogleLoginService,
        links: GoogleLinkService,
        email_links: GoogleEmailLinkService,
    ) -> None:
        self.accounts, self.links, self.email_links = accounts, links, email_links

    def complete(
        self,
        result: GoogleCallbackResult,
        browser_token: str | None,
        session_token: str | None,
        *,
        user_agent: str | None = None,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> IssuedSession | GoogleEmailDelivery:
        identity, context = result.identity, result.link
        if context is not None:
            if (
                not identity.email_authoritative
                and self.links.identities.get_user_id(identity.subject) is None
            ):
                return self.email_links.prepare(
                    context.user_id, identity, browser_token, context, session_token
                )
            return self.links.complete(
                identity, context, session_token, user_agent=user_agent, ip_address=ip_address
            )
        try:
            return self.accounts.login(identity, user_agent=user_agent, ip_address=ip_address)
        except AccountLinkingRequired:
            if identity.email_authoritative:
                raise
            user_id = self.accounts.email_link_target(identity)
            return self.email_links.prepare(user_id, identity, browser_token)
