# ADR 0008: Require Completed Registration

Date: 2026-10-16
Status: accepted by the repository owner and implemented.

## Decision

Application access requires an active user, verified canonical email and a password
credential. Password registration creates a restricted registration session until
email confirmation. A Google registration must set an Ukladen password before
application access. Gmail and Google Workspace identity claims validated by the
backend can establish email ownership; other Google emails require our email proof.

An unlinked authoritative Google identity may attach automatically only to an
active account whose matching canonical email is already verified. An unverified
existing account is not silently claimed or merged. Existing identities never move
between users. Other first-time Google links require fresh mailbox confirmation.

Pending sessions may inspect registration state, set a missing password, request
verification and log out. They may not access business APIs. Readiness is checked
against canonical PostgreSQL data, including when session authentication is cached.
No raw provider token is persisted. Existing account data is preserved.

Recovery must revoke previous sessions and must not retain attacker-controlled
external identities from an unverified registration. Re-registration never replaces
an existing credential. Existing passwordless Google users must set a password;
existing unverified users must complete verification.

## Security amendment — 2026-10-17

Email-verification confirmation requires an active registration session belonging
to the token's user, in addition to mailbox proof and CSRF. A link opened by an
anonymous browser or another account must not activate credentials supplied by a
third party. The same registration browser confirms automatically; on another device
sign in to the same account first, then reopen the email link. Unknown registrations
use mailbox-based password recovery, which replaces the password and revokes prior
sessions/identities. Anonymous verification from the earlier API is intentionally
rejected with 401; mismatched ownership returns the generic invalid-token error.

Password reset/change invalidates all earlier outstanding reset tokens atomically.
Confirmation locks the user before the token so competing sibling reset links cannot
deadlock or restore an earlier credential. Login and reset-request limits apply to
both the peer address and normalized email, preventing source-address rotation from
bypassing a target's limit. Frontend authentication pages cannot be framed.

## Consequences

This replaces the earlier policy allowing application use before email verification
and requiring password confirmation for every initial Google link. Opaque browser
sessions, CSRF, nonce, PKCE, browser binding, rate limits and adapter boundaries remain.
Registration screens must explain the next step and offer bounded resend/recovery.
Verification history in existing documentation remains historical.
