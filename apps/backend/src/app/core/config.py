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
    auth_email_delivery_mode: Literal["disabled", "fake"] = "disabled"
    google_client_id: str | None = Field(default=None, min_length=1, max_length=1024)
    google_client_secret: SecretStr | None = Field(default=None, min_length=1, repr=False)
    google_redirect_uri: AnyHttpUrl | None = None

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
        return self

    @model_validator(mode="after")
    def validate_browser_auth(self) -> Settings:
        names = (self.auth_session_cookie_name, self.auth_csrf_cookie_name)
        if names[0] == names[1]:
            raise ValueError("Session and CSRF cookie names must differ.")
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
