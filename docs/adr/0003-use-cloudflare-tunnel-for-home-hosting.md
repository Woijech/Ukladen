# ADR 0003: Use Cloudflare Tunnel for Home Hosting

Date: 2026-10-04
Status: accepted by the repository owner for hosting `ukladen.app` on their PC.

## Decision

Reuse the existing Compose stack and Traefik. Add the official cloudflared
connector for an outbound, remotely managed Cloudflare Tunnel. Cloudflare manages
the public DNS and browser TLS certificate; the domain remains registered at
name.com. No router forwarding or public service ports are needed.

The home overlay uses an isolated edge network with explicit trusted proxy
addresses. Authentication retains opaque sessions, Secure cookies, exact-origin
CSRF validation and existing token rules. SMTP delivery remains independent.
The backend remains a modular monolith. No Python/JavaScript dependency is added.

## Consequences

Cloudflare becomes an external DNS/traffic/TLS dependency and terminates browser
TLS. Its tunnel token is a secret held in the ignored private deployment env file.
The PC must stay powered and connected. Existing single-node data services remain;
this does not select a production storage provider, implement backups/redundancy,
or expand the unfinished product UI. Public activation is separate from checked-in
configuration and requires completing Cloudflare account/DNS setup.

Implementation and setup: [home server](../deployment/home-server.md).
