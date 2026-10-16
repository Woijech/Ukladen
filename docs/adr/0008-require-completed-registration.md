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

## Consequences

This replaces the earlier policy allowing application use before email verification
and requiring password confirmation for every initial Google link. Opaque browser
sessions, CSRF, nonce, PKCE, browser binding, rate limits and adapter boundaries remain.
Registration screens must explain the next step and offer bounded resend/recovery.
Verification history in existing documentation remains historical.
