# Users Profile API

Status: implemented, backend only.

The users module owns the canonical `users` table. Registration, verification,
credentials, linked identities and opaque browser sessions keep their existing
contracts. Email/password changes and session management remain in auth.

## Fields

| Field | Default | Validation |
| --- | --- | --- |
| `display_name` | `null` | String trimmed with Python `str.strip()`, 1–100 characters after trimming, or explicit null to clear. |
| `timezone` | `UTC` | Nonempty string accepted by standard-library `zoneinfo.ZoneInfo`; unknown identifiers and null are rejected. |
| `locale` | `ru` | Exactly `ru` or `en`; null is rejected. |

The backend image already includes system timezone data. Runtime verification
checked `UTC`, `Europe/Minsk` and `America/New_York`; no timezone package or image
change was required. Keep timezone data available when changing the base image.
Timezone is a stored preference; API timestamps remain timezone-aware instants.

## Endpoints and security

`GET /api/v1/users/me` requires an active authenticated session and reads canonical
data from PostgreSQL. It does not change `updated_at` or any profile data.

`PATCH /api/v1/users/me` requires the same session, an exact allowed `Origin` and
the existing CSRF cookie plus matching `X-CSRF-Token` header. Bootstrap the cookie
and JSON token through `GET /api/v1/auth/csrf`. Both endpoints return HTTP 200 with
`Cache-Control: no-store` and the same response fields:

```json
{
  "id": "1d5c238a-0764-4aeb-9a36-67b918f04040",
  "email": "student@example.com",
  "email_verified_at": null,
  "status": "active",
  "display_name": "Alex",
  "timezone": "Europe/Minsk",
  "locale": "ru",
  "avatar_url": null,
  "created_at": "2026-10-05T09:00:00Z",
  "updated_at": "2026-10-05T09:15:00Z"
}
```

Values above are illustrative; IDs and timestamps come from the stored account.
New or migrated accounts initially return `display_name: null`, `timezone: UTC`
and `locale: ru`. Unverified active users and Google-only accounts are eligible.
The response contains no credentials, tokens, hashes or internal auth records.
`avatar_url` is null when no avatar exists, otherwise `/api/v1/users/me/avatar`.
Avatar changes use the separate [avatar API](user-avatar.md); `avatar_key` and
`avatar_url` cannot be supplied in the profile patch.

The patch accepts only the three profile fields. Omitted fields stay unchanged;
`{"display_name": null}` clears the name. `{}` is invalid. Fields such as `id`,
`user_id`, `email`, `email_verified_at`, `status`, `created_at`, `updated_at` and
`preferences` are rejected, even alongside valid fields. The session always
determines the target user. Successful patches change only supplied columns and
`updated_at`; passwords, identities, tokens, sessions and other users are preserved.

Eligibility is checked again against canonical user data during the profile
operation. Atomic updates constrain both user UUID and active status and avoid
writing omitted columns, including while waiting for a concurrent update. A
response is returned only after the caller-owned database transaction commits.
Write/commit failures roll back the entire patch.

| Status | Meaning |
| --- | --- |
| `200` | Profile read or committed update. |
| `401` | Missing, invalid, expired or revoked session, or missing/disabled canonical user; the existing auth handler clears the session cookie. |
| `403` | Missing/invalid CSRF cookie/header or disallowed/missing Origin. |
| `422` | Invalid JSON, unsupported fields, empty patch or invalid field value; generic `Invalid request.` without input echo. |
| `503` | Database/commit failure; generic `Service unavailable.` without connection details. |

These responses use `Cache-Control: no-store`. Profile validation does not log
request values or database errors. No new rate limit or email operation is added.
OpenAPI is available at `/api/openapi.json` and interactive docs at `/api/docs`.

## Runnable local example

Use an existing password account and a configured allowed local origin. This flow
uses the existing login endpoint and sends no verification email. For a Google-only
account, use its existing authenticated browser cookie instead of password login.
Python is used only to encode credentials safely and extract the CSRF token.

```bash
profile_origin=http://localhost:8080
profile_cookie_jar=$(mktemp)
read -r -p 'Email: ' profile_email
read -r -s -p 'Password: ' profile_password
export profile_email profile_password

profile_csrf=$(curl --fail --silent --show-error \
  -c "$profile_cookie_jar" -b "$profile_cookie_jar" \
  "$profile_origin/api/v1/auth/csrf" \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["csrf_token"])')

python3 -c 'import json, os; print(json.dumps({"email": os.environ["profile_email"], "password": os.environ["profile_password"]}))' \
  | curl --fail --silent --show-error \
    -c "$profile_cookie_jar" -b "$profile_cookie_jar" \
    -H "Origin: $profile_origin" -H "X-CSRF-Token: $profile_csrf" \
    -H 'Content-Type: application/json' --data-binary @- \
    "$profile_origin/api/v1/auth/login"
unset profile_email profile_password

curl --fail --silent --show-error -b "$profile_cookie_jar" \
  "$profile_origin/api/v1/users/me"

curl --fail --silent --show-error -b "$profile_cookie_jar" \
  -H "Origin: $profile_origin" -H "X-CSRF-Token: $profile_csrf" \
  -H 'Content-Type: application/json' -X PATCH \
  --data '{"display_name":" Alex ","timezone":"Europe/Minsk","locale":"ru"}' \
  "$profile_origin/api/v1/users/me"

curl --fail --silent --show-error -b "$profile_cookie_jar" \
  -H "Origin: $profile_origin" -H "X-CSRF-Token: $profile_csrf" \
  -H 'Content-Type: application/json' -X PATCH \
  --data '{"display_name":null}' "$profile_origin/api/v1/users/me"
rm "$profile_cookie_jar"
```

GET returns the existing profile. The first PATCH returns the profile with name
`Alex`, timezone `Europe/Minsk` and locale `ru`; the second returns a null name while
preserving timezone and locale. Both PATCH responses have an updated timestamp.
Use HTTPS and the configured public origin for deployment cookies.

## Migration and verification

`0003_users_profile` follows `0002_auth_persistence`. It adds the profile columns
with database defaults so existing users and unchanged registration paths remain
valid. PostgreSQL enforces nullable names of 1–100 characters without surrounding
POSIX whitespace, nonempty/non-null timezone and non-null supported locale.
Full Unicode trimming and timezone identifier validation occur in domain/transport
validation; PostgreSQL does not validate IANA identifiers against its own timezone
catalog. This avoids coupling application validation to a second timezone catalog.

Upgrade changes no existing auth/user values or timestamps. Downgrade to
`0002_auth_persistence` removes only profile columns and their constraints, losing
profile values while preserving users and authentication records. Integration
tests verify both directions with existing password and Google-only accounts.
Apply through the usual migration process:

```bash
cd apps/backend
uv run --env-file ../../.env alembic upgrade head
```

Do not run a downgrade against a deployment merely to test it. Tests use unique
PostgreSQL schemas, generated Redis session keys and injected/fake providers.
Enable the existing integration configuration against disposable test services:

```bash
export AUTH_TEST_DATABASE_URL='postgresql+psycopg://TEST_USER:TEST_PASSWORD@localhost:5432/TEST_DATABASE'
export AUTH_TEST_REDIS_URL='redis://localhost:6379/15'
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

`test_users_profile*.py` covers validation, defaults, partial updates, safe fields,
session/CSRF rejection, ownership, independent-session persistence, failed-write
and failed-commit rollback, preservation of auth records, canonical eligibility,
concurrent partial updates and migration compatibility. Integration tests skip
when their test URLs are unset. Tests send no external email or Google requests.

Frontend, academic profiles, groups, account deletion, administrative
management and public user lookup are outside this slice and not implemented here.
