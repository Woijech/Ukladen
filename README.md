# Ukladen

## Project Overview

Ukladen is a personal student productivity platform that combines:

- BSUIR university schedule;
- a flexible personal calendar;
- tasks and deadlines;
- reminders;
- notes;
- study materials;
- relations between workspace entities;
- search;
- an AI assistant;
- RAG over user materials.

The product concept combines ideas from **Google Calendar**, **Notion**, and task management systems while being specialized for the workflow of a BSUIR student.

Status: the product flows below are planned and not implemented.

## Core Idea

After registration, the user selects a university group and optionally a subgroup.

The system retrieves schedule data through the BSUIR IIS integration and creates a personal calendar view.

The imported university schedule is not treated as an immutable personal plan.

For example, a student can:

- mark a lecture as skipped;
- free that interval in the personal calendar;
- place a personal event in that time slot;
- attach notes;
- link tasks;
- attach study materials;
- create reminders.

Official schedule data and personal calendar state are logically separated.

## Architecture

Primary architecture document:

```text
SYSTEM_ARCHITECTURE.md
```

Architecture style:

```text
Modular Monolith
```

Main runtime components:

```text
Next.js Frontend
       |
       v
FastAPI Backend
       |
 +-----+---------+----------+
 |               |          |
 v               v          v
PostgreSQL      Redis     SeaweedFS/S3
+ pgvector        |
                  v
             Celery Workers
```

## Technology Stack

### Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
httpx
```

### Data

```text
PostgreSQL
pgvector
PostgreSQL Full Text Search
Redis
```

### Async Processing

```text
Celery
Celery Beat
```

### Files

```text
SeaweedFS
S3-compatible object storage
```

### Frontend

```text
Next.js
React
TypeScript
TanStack Query
Zustand
FullCalendar
```

### DevOps

```text
Docker
Docker Compose
Traefik
GitHub Actions
```

### Quality

```text
uv
Ruff
Pyright
pytest
Playwright
```

## Backend Modules

```text
auth
users
academics
subjects
schedule
calendar
tasks
reminders
notes
materials
relations
search
ai
notifications
integrations
```

## Development Rules

Mandatory rules for AI coding agents and human developers are defined in:

```text
AGENTS.md
```

## Documentation Language

All technical documentation and code comments are written in English.

User-facing product text may initially be Russian.

## Current Status

Phase 0 foundation is implemented. The repository contains a FastAPI modular
monolith, Next.js shell, PostgreSQL 18/pgvector, Redis, Celery worker and Beat,
SeaweedFS object storage, Traefik, Docker Compose and GitHub Actions CI.
Authentication is partially implemented: application registration, email
verification and password reset, plus browser password login/logout, session
management, password change, email-verification confirmation and password-reset
confirmation. Celery email queuing with a development fake is implemented.
Registration and password-reset requests queue messages after commit.
A Google OIDC adapter validates provider identities, and an application service
resolves Google accounts into ordinary sessions. Google browser login, production
email delivery and authentication UI are not implemented.

```text
apps/backend     Python 3.14 API, module boundaries, migrations, workers, tests
apps/web         Next.js/React/TypeScript shell and browser tests
infra            Traefik routing
docs            Architecture, product and local development documents
```

Start from the repository root:

```bash
cp .env.example .env
docker compose up --build --detach --wait --wait-timeout 180
```

Open <http://localhost:8080> and <http://localhost:8080/api/docs>.
All published ports bind to localhost. The first image build requires network
access to download dependencies and images. These are local development settings.

If `.env` already exists, copy the browser authentication settings from
`.env.example` into it for local HTTP access. Production defaults use Secure
`__Host-` cookies; local HTTP uses distinct unprefixed cookies with
`AUTH_COOKIE_SECURE=false`. Set `AUTH_ALLOWED_ORIGINS` to the exact frontend
origins (HTTPS in production). This allowlist provides CSRF validation, not CORS.

`AUTH_EMAIL_DELIVERY_MODE` defaults to `disabled`. `.env.example` explicitly uses
`fake` for development: queued verification/reset messages are captured only in
worker memory, without sending external email or logging tokens. Existing `.env`
files are not changed automatically. A production mail provider is not implemented;
keep delivery disabled outside development. Registration and password-reset requests
use this queue.

For browser password login, call `GET /api/v1/auth/csrf` with cookies enabled,
retain its `csrf_token`, then send it as `X-CSRF-Token` together with cookies and
the browser's `Origin` on `POST /api/v1/auth/login` (`email` and `password` JSON).
Successful login delivers an HttpOnly session cookie after committing the session.
`POST /api/v1/auth/logout` and `/api/v1/auth/logout-all` require the same CSRF
protection and return 204 after revocation. Login permits 10 attempts per client
address per 60-second window by default.

Register with `POST /api/v1/auth/register`, sending `email` and `password` in JSON
with the same CSRF protection. Passwords accept 12–1024 characters by default;
whitespace and Unicode are preserved. Success returns 201 with user/session IDs
and expiry, sets the session cookie and queues verification email only after the
account, credential, session and hashed verification token commit. The default
limit is five attempts per client address per 60-second window, configurable with
`AUTH_REGISTER_RATE_LIMIT` and `AUTH_REGISTER_RATE_WINDOW_SECONDS`. Invalid input
returns 400, duplicate emails 409, invalid transport 422 and database failures 503;
none issues a session cookie. Disabled email delivery returns 503 before creation.
A queue failure after commit retains 201 and the session, with safe metadata-only
logging; the account remains unverified. There is no durable publication recovery.
Users may log in before verification and request another verification message.

The Google adapter is configured with `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
and `GOOGLE_REDIRECT_URI`; leave all three unset to disable it, or configure all
three together. Redirect URIs require HTTPS except for local loopback development,
and cannot contain credentials, query strings or fragments. `.env.example` provides
commented placeholders; existing `.env` files are not changed. The adapter uses
Google discovery/JWKS data, PKCE and signed ID-token validation, returning only the
verified Google subject and normalized email. `PyJWT[crypto]` supplies RSA validation;
Ukladen browser authentication continues to use opaque server-side sessions.
Account resolution authenticates linked subjects, creates verified Google-only
users for unused emails, and requires explicit linking when an email already exists.
It preserves existing accounts and commits user, identity and session together.
Google start/callback endpoints, browser-bound Redis state and explicit linking
are not implemented. Configuring credentials does not enable
Google login yet. Tests use mocked HTTP and in-memory signing keys, with no Google
network calls.

Authenticated clients can change their password with
`POST /api/v1/auth/password/change`, sending `current_password` and `new_password`
in JSON with the same cookies, `Origin` and CSRF header. Success returns 204,
keeps the current session and revokes other sessions. The default limit is five
attempts per user per 60-second window. The new password must meet the configured
registration length policy; the default minimum is 12 characters.

Email-verification tokens can be confirmed with
`POST /api/v1/auth/email-verification/confirm`, sending `token` in JSON with the
CSRF cookie, allowed `Origin` and CSRF header. Login is unnecessary. Success
returns an empty 204, consumes the token and verifies its user's email without
changing session cookies. Invalid, expired or used tokens return a generic 400;
malformed request bodies return a generic 422. The default limit is five attempts
per client address per 60-second window. Registration queues verification messages
through the development fake; real email delivery remains unimplemented.

Signed-in users can resend verification with
`POST /api/v1/auth/email-verification/request`, sending `{}` in JSON with the
session cookie and the same CSRF protection. The server uses the current user's
stored email; caller-supplied recipients are rejected. Success returns 202 and
`Email verification request accepted.`, retaining the session cookie. Already
verified users receive the same acknowledgement without mail or a new token.
The default limit is five requests per user per 60-second window, configured with
`AUTH_EMAIL_VERIFICATION_REQUEST_RATE_LIMIT` and
`AUTH_EMAIL_VERIFICATION_REQUEST_RATE_WINDOW_SECONDS`. Disabled delivery returns
503 before issuance. The token commits before queuing; queue failure retains 202,
so the user can request another message. Earlier unused tokens stay valid until
their original expiry, and each token remains single-use.

Password-reset tokens can be confirmed with
`POST /api/v1/auth/password-reset/confirm`, sending `token` and `new_password` in
JSON with the same CSRF protection. Login is unnecessary. Success returns an empty
204 after updating the password, consuming the token and revoking all of the
account's sessions; it clears the browser session cookie. The new password uses
the configured registration length policy. Invalid tokens and policy failures
return fixed 400 errors; malformed request bodies return a generic 422. The
default limit is five attempts per client address per 60-second window.

Request a reset with `POST /api/v1/auth/password-reset/request`, sending `email` in
JSON with the same CSRF protection; login is unnecessary. With fake delivery enabled,
all account outcomes return 202 and `Password reset request accepted.` Eligible
accounts receive a hashed reset token in PostgreSQL, committed before its email
message is queued. Disabled delivery returns a generic 503 before account lookup.
The default request limit is five attempts per client address per minute. Requests
preserve session cookies and never return tokens or account details. Queue failure
after commit still returns the generic acknowledgement, with only safe server
metadata logged; clients can retry. There is no durable delivery guarantee or
production mail provider, and fake messages remain only in worker memory.

Read [Local Development](docs/development/local-development.md) for host setup,
checks and troubleshooting. Implementation details are in
[Architecture Overview](docs/architecture/overview.md),
[Backend](docs/architecture/backend.md), [Frontend](docs/architecture/frontend.md)
and [Infrastructure](docs/architecture/infrastructure.md).

Local storage uses SeaweedFS; [ADR 0001](docs/adr/0001-use-seaweedfs.md) records
the provider decision. Production storage remains a separate deployment decision.
Authentication is partially implemented as described above. Real IIS integration,
calendar, tasks, notes, materials, search, AI and RAG remain **not implemented**.
