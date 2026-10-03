# Authentication Email Delivery

Status: SMTP delivery, fake delivery and disabled mode are implemented.
Frontend authentication forms, automatic delivery retries and durable publication
recovery are not implemented.

Registration, verification resend and password-reset requests commit their
single-use token hashes to PostgreSQL, then enqueue `auth.send_email` through the
existing `EmailSender` port. The Celery worker sends the message. No schema change,
external vendor SDK or new Python dependency is required.

## SMTP Setup

Obtain the SMTP host, port, security mode, credentials and authorized sender address
from your chosen SMTP service. Its sender/domain authorization and delivery rules
must be configured with that service. Add these settings to your ignored `.env`:

```dotenv
AUTH_EMAIL_DELIVERY_MODE=smtp
SMTP_HOST=smtp.your-service.example
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME='your-smtp-username'
SMTP_PASSWORD='your-smtp-password'
SMTP_FROM_EMAIL=noreply@your-authorized-domain.example
SMTP_TIMEOUT_SECONDS=10
```

Use `SMTP_SECURITY=tls` with port 465 when the service requires implicit TLS.
Both encrypted modes verify certificates and hostnames. There is no insecure TLS
fallback. Username/password are optional only for a relay that does not require
authentication; otherwise provide both. Never commit `.env` or credentials.

For local HTTP, retain these settings from `.env.example`. Quote the complete JSON
origin list so that both dotenv readers and `uv --env-file` preserve its contents:

```dotenv
AUTH_SESSION_COOKIE_NAME=ukladen_session
AUTH_CSRF_COOKIE_NAME=ukladen_csrf
AUTH_OAUTH_COOKIE_NAME=ukladen_oauth
AUTH_COOKIE_SECURE=false
AUTH_ALLOWED_ORIGINS='["http://localhost:8080","http://localhost:3000","http://localhost:8000"]'
```

From the repository root, refresh the stack:

```bash
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 180
docker compose exec -T worker celery -A app.workers.celery_app:celery_app inspect ping --timeout 5
```

Compose already forwards `.env` to the API and worker. Their delivery settings
must match; rebuild after source changes and recreate both processes after changing
configuration. For host development, launch both Uvicorn and the Celery worker
with `uv run --env-file ../../.env` from `apps/backend`, as described in
[local development](local-development.md). The worker needs outbound connectivity
to the configured SMTP host/port. `localhost` inside a container refers to that
container, so a local receiver must have an address reachable from the worker.

An existing trusted local SMTP receiver can use `SMTP_SECURITY=none`, its listening
port and no username/password. This is explicit development-only plaintext
transport. No receiver is installed automatically. For deployment, use TLS, the
production Secure cookie defaults and HTTPS origins, and supply secrets through
your deployment environment. Production deployment automation remains outside
the local Compose setup.

## End-to-End Email Verification

Use an email address whose inbox you control. The following Bash session keeps
cookies and CSRF protection across requests. Replace the placeholder email and
password. Passwords require at least 12 characters by default.

```bash
AUTH_BASE=http://localhost:8080
AUTH_COOKIE_JAR=$(mktemp)
read -r -p 'Your email address: ' AUTH_EMAIL
IFS= read -r -s -p 'Test account password: ' AUTH_PASSWORD
echo
AUTH_CSRF=$(curl -fsS -c "$AUTH_COOKIE_JAR" "$AUTH_BASE/api/v1/auth/csrf" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])')

# Reuse the same cookies, Origin and CSRF header for every mutation.
auth_post() {
  curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
    -b "$AUTH_COOKIE_JAR" -c "$AUTH_COOKIE_JAR" \
    -H "Origin: $AUTH_BASE" -H "X-CSRF-Token: $AUTH_CSRF" \
    -H 'Content-Type: application/json' \
    --data-binary @- "$AUTH_BASE/api/v1/auth/$1"
}

# Expected: HTTP 201. Registration also creates a session.
printf '%s\n%s\n' "$AUTH_EMAIL" "$AUTH_PASSWORD" |
  python3 -c 'import json,sys; print(json.dumps(dict(zip(("email","password"), sys.stdin.read().splitlines()))))' |
  auth_post register
```

The worker should send a message with subject `Verify your Ukladen email`. Copy
the token from the private email body, then submit it without putting it in a URL:

```bash
read -r -s -p 'Verification token from your email: ' AUTH_VERIFY_TOKEN
echo
printf '%s' "$AUTH_VERIFY_TOKEN" |
  python3 -c 'import json,sys; print(json.dumps({"token":sys.stdin.read()}))' |
  auth_post email-verification/confirm
unset AUTH_VERIFY_TOKEN
```

Expected: HTTP 204. Repeating confirmation with the same token returns HTTP 400.
Verification expiry defaults to 24 hours from issuance, including time waiting in
the queue. The current session remains valid. Before confirming, test resend with:

```bash
printf '{}' | auth_post email-verification/request
```

Expected: HTTP 202 and another verification email. This requires the registration
session or another logged-in session. After verification, the endpoint still
returns 202 but sends no email. There is no public token inbox or frontend
verification page; confirmation currently uses the API above.

## End-to-End Password Reset

Continue in the same Bash session, using an existing password account:

```bash
printf '%s' "$AUTH_EMAIL" |
  python3 -c 'import json,sys; print(json.dumps({"email":sys.stdin.read()}))' |
  auth_post password-reset/request
```

Expected: HTTP 202. The response is identical for unknown or ineligible accounts;
only eligible password accounts receive `Reset your Ukladen password` email.
Request and confirmation need CSRF protection but do not require login.

```bash
read -r -s -p 'Reset token from your email: ' AUTH_RESET_TOKEN
echo
IFS= read -r -s -p 'New password (at least 12 characters): ' AUTH_NEW_PASSWORD
echo
printf '%s\n%s\n' "$AUTH_RESET_TOKEN" "$AUTH_NEW_PASSWORD" |
  python3 -c 'import json,sys; print(json.dumps(dict(zip(("token","new_password"), sys.stdin.read().splitlines()))))' |
  auth_post password-reset/confirm
unset AUTH_RESET_TOKEN

# Expected: HTTP 200 with the new password.
printf '%s\n%s\n' "$AUTH_EMAIL" "$AUTH_NEW_PASSWORD" |
  python3 -c 'import json,sys; print(json.dumps(dict(zip(("email","password"), sys.stdin.read().splitlines()))))' |
  auth_post login
```

Reset confirmation returns HTTP 204, consumes the token, revokes all account
sessions and clears the session cookie. The old password should now return HTTP
401 on login; repeating confirmation with the reset token returns HTTP 400.
Reset tokens expire one hour after issuance by default.

After testing, log out and clear local test variables/files:

```bash
printf '{}' | auth_post logout
rm -f "$AUTH_COOKIE_JAR"
unset AUTH_PASSWORD AUTH_NEW_PASSWORD AUTH_CSRF
```

## Delivery Failures and Automated Checks

An HTTP 201/202 acknowledges account/token creation and publication attempt,
not inbox delivery. Check that the worker runs and that your SMTP service accepts
the configured sender, credentials and TLS mode. Worker errors deliberately use
`Email delivery is unavailable.` without provider exception text or message bodies.
Use the SMTP service's delivery status for downstream rejection/bounce diagnosis.
Do not enable SMTP debug output or log Celery payloads: they contain private tokens.

There is no transactional outbox, automatic retry or durable SMTP idempotency.
Broker/worker outages can lose email; users can request a new message. Duplicate
delivery never makes an already consumed token usable again. PostgreSQL continues
to store only hashes, and token contents never appear in API responses or logs.

Keep `AUTH_EMAIL_DELIVERY_MODE=fake` for development without delivery, or `disabled`
to refuse email-dependent operations. Automated tests retain the fake, mock TLS
transports and use a loopback-only SMTP receiver without contacting a mail vendor.
PostgreSQL/Redis integration tests use isolated schemas and generated broker keys.

From `apps/backend`, using dedicated test database/Redis settings:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
AUTH_TEST_DATABASE_URL=postgresql+psycopg://test-user:test-password@localhost:5432/test-db \
AUTH_TEST_REDIS_URL=redis://localhost:6379/15 \
  uv run pytest
```

Without the two integration variables, PostgreSQL/Redis checks are skipped.
Loopback SMTP transmission tests run without those external services; the
combined HTTP/queue/SMTP test requires both. No automated test sends external mail.
