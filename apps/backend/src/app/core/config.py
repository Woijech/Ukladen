from email.errors import HeaderParseError
from email.headerregistry import Address
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: PostgresDsn
    redis_url: RedisDsn
    s3_endpoint: AnyHttpUrl
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket: str = Field(min_length=1)
    auth_session_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    auth_password_min_length: int = Field(default=12, gt=0, le=1024)
    auth_email_verification_ttl_seconds: int = Field(default=24 * 60 * 60, gt=0)
    auth_password_reset_ttl_seconds: int = Field(default=60 * 60, gt=0)
    auth_oauth_state_ttl_seconds: int = Field(default=10 * 60, gt=0)
    auth_session_cookie_name: str = Field(
        default="__Host-ukladen_session", pattern=r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$"
    )
    auth_csrf_cookie_name: str = Field(
        default="__Host-ukladen_csrf", pattern=r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$"
    )
    auth_oauth_cookie_name: str = Field(
        default="__Host-ukladen_oauth", pattern=r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$"
    )
    auth_cookie_secure: bool = True
    auth_cookie_samesite: Literal["lax", "strict"] = "lax"
    auth_allowed_origins: list[AnyHttpUrl] = Field(default_factory=list)
    auth_login_rate_limit: int = Field(default=10, gt=0)
    auth_login_rate_window_seconds: int = Field(default=60, gt=0)
    auth_register_rate_limit: int = Field(default=5, gt=0)
    auth_register_rate_window_seconds: int = Field(default=60, gt=0)
    auth_password_change_rate_limit: int = Field(default=5, gt=0)
    auth_password_change_rate_window_seconds: int = Field(default=60, gt=0)
    auth_email_verification_confirm_rate_limit: int = Field(default=5, gt=0)
    auth_email_verification_confirm_rate_window_seconds: int = Field(default=60, gt=0)
    auth_email_verification_request_rate_limit: int = Field(default=5, gt=0)
    auth_email_verification_request_rate_window_seconds: int = Field(default=60, gt=0)
    auth_password_reset_confirm_rate_limit: int = Field(default=5, gt=0)
    auth_password_reset_confirm_rate_window_seconds: int = Field(default=60, gt=0)
    auth_password_reset_request_rate_limit: int = Field(default=5, gt=0)
    auth_password_reset_request_rate_window_seconds: int = Field(default=60, gt=0)
    auth_email_delivery_mode: Literal["disabled", "fake", "smtp"] = "disabled"
    smtp_host: str | None = Field(default=None, min_length=1, max_length=253, pattern=r"^[\w.:-]+$")
    smtp_port: int = Field(default=587, gt=0, le=65535)
    smtp_security: Literal["starttls", "tls", "none"] = "starttls"
    smtp_username: SecretStr | None = Field(default=None, min_length=1, repr=False)
    smtp_password: SecretStr | None = Field(default=None, min_length=1, repr=False)
    smtp_from_email: str | None = Field(default=None, min_length=1, max_length=320)
    smtp_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    google_client_id: str | None = Field(default=None, min_length=1, max_length=1024)
    google_client_secret: SecretStr | None = Field(default=None, min_length=1, repr=False)
    google_redirect_uri: AnyHttpUrl | None = None
    frontend_auth_success_url: AnyHttpUrl | None = None
    frontend_auth_error_url: AnyHttpUrl | None = None
    auth_google_start_rate_limit: int = Field(default=10, gt=0)
    auth_google_start_rate_window_seconds: int = Field(default=60, gt=0)
    auth_google_callback_rate_limit: int = Field(default=10, gt=0)
    auth_google_callback_rate_window_seconds: int = Field(default=60, gt=0)
    auth_google_link_rate_limit: int = Field(default=5, gt=0)
    auth_google_link_rate_window_seconds: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def validate_smtp(self) -> Settings:
        if self.auth_email_delivery_mode != "smtp":
            return self
        if self.smtp_host is None or self.smtp_from_email is None:
            raise ValueError("SMTP delivery requires a host and sender email address.")
        credentials = (self.smtp_username, self.smtp_password)
        if any(value is not None for value in credentials) and any(
            value is None for value in credentials
        ):
            raise ValueError("SMTP username and password must be configured together.")
        if self.smtp_security == "none" and self.smtp_username is not None:
            raise ValueError("SMTP authentication requires TLS.")
        try:
            address = Address(addr_spec=self.smtp_from_email)
        except ValueError, HeaderParseError:
            raise ValueError("SMTP sender must be a bare email address.") from None
        if not address.username or not address.domain or address.addr_spec != self.smtp_from_email:
            raise ValueError("SMTP sender must be a bare email address.")
        return self

    @model_validator(mode="after")
    def validate_google(self) -> Settings:
        configured = (self.google_client_id, self.google_client_secret, self.google_redirect_uri)
        if any(value is not None for value in configured) and any(
            value is None for value in configured
        ):
            raise ValueError("Google configuration requires client ID, secret and redirect URI.")
        uri = self.google_redirect_uri
        if uri is not None and (
            uri.username
            or uri.password
            or uri.query
            or uri.fragment
            or (uri.scheme != "https" and uri.host not in ("localhost", "127.0.0.1", "[::1]"))
        ):
            raise ValueError("Google redirect URI requires HTTPS, except for local development.")
        frontend = (self.frontend_auth_success_url, self.frontend_auth_error_url)
        if any(url is not None for url in frontend) and any(url is None for url in frontend):
            raise ValueError("Frontend authentication redirects must be configured together.")
        for url in frontend:
            if url is not None and (
                url.username
                or url.password
                or url.query
                or url.fragment
                or (url.scheme != "https" and url.host not in ("localhost", "127.0.0.1", "[::1]"))
            ):
                raise ValueError(
                    "Frontend authentication redirects require HTTPS or loopback HTTP."
                )
        return self

    @model_validator(mode="after")
    def validate_browser_auth(self) -> Settings:
        names = (self.auth_session_cookie_name, self.auth_csrf_cookie_name)
        if names[0] == names[1]:
            raise ValueError("Session and CSRF cookie names must differ.")
        if self.auth_oauth_cookie_name in names:
            raise ValueError("OAuth cookie name must differ from session and CSRF names.")
        if self.frontend_auth_success_url is not None:
            names += (self.auth_oauth_cookie_name,)
        if not self.auth_cookie_secure and any(
            name.startswith(("__Host-", "__Secure-")) for name in names
        ):
            raise ValueError("Prefixed authentication cookies require Secure.")
        for origin in self.auth_allowed_origins:
            if (
                origin.username
                or origin.password
                or origin.path not in (None, "/")
                or origin.query
                or origin.fragment
            ):
                raise ValueError(
                    "Authentication origins must contain only a scheme, host and optional port."
                )
        return self


def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
