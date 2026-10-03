class AuthError(Exception):
    """Base authentication domain error."""


class InvalidSession(AuthError):
    """The session is expired, revoked or not yet valid."""


class SessionNotFound(AuthError):
    """The requested session is missing or belongs to another user."""


class InvalidOneTimeToken(AuthError):
    """The token is expired, consumed or not yet valid."""


class InvalidRegistration(AuthError):
    """The email or password does not satisfy registration requirements."""


class RegistrationConflict(AuthError):
    """The email address already belongs to an account."""


class InvalidCredentials(AuthError):
    """The supplied credentials cannot authenticate an active user."""


class InvalidPassword(AuthError):
    """The proposed password does not satisfy the current password policy."""


class InvalidExternalIdentity(AuthError):
    """The provider response cannot establish a verified identity."""
