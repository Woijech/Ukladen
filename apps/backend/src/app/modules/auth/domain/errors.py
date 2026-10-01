class AuthError(Exception):
    """Base authentication domain error."""


class InvalidSession(AuthError):
    """The session is expired, revoked or not yet valid."""


class InvalidOneTimeToken(AuthError):
    """The token is expired, consumed or not yet valid."""
