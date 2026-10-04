# Home server with Cloudflare Tunnel

Status: deployment configuration implemented. Public activation requires a Cloudflare
account, an active `ukladen.app` DNS zone and a remotely managed tunnel token.
This publishes the existing Next.js shell, API and email-verification page;
registration/login/reset screens and the student workspace are not implemented.

The PC runs the existing modular monolith and its data services. The only new
component is the official `cloudflared` connector. Browser TLS terminates at
Cloudflare; the outbound tunnel is encrypted. Its origin is Traefik over HTTP
inside a dedicated Docker network on the same PC. No inbound router ports,
public IP, ACME certificate or separate web server is required.

## 1. Add the domain

1. Sign in to [Cloudflare](https://dash.cloudflare.com/), choose **Add a domain /
   Onboard a domain**, enter `ukladen.app`, and select the Free plan.
2. Review the imported DNS records, including existing MX/TXT records used by
   email. A tunnel replaces only the web hostname, not your SMTP provider.
3. If DNSSEC is enabled at name.com, disable it before replacing nameservers.
4. In name.com, open **My Domains → ukladen.app → Manage Nameservers**. Replace
   the existing nameservers with the two assigned to this domain by Cloudflare.
   Keep the domain registered at name.com; no domain transfer is needed.
5. Wait until Cloudflare reports the domain as **Active**. Re-enable DNSSEC using
   Cloudflare's DS information at the registrar if desired.
6. Wait for the Universal SSL edge certificate to become active. Enable **Always
   Use HTTPS** under **SSL/TLS → Edge Certificates**. `.app` requires HTTPS.

Do not create an A record pointing to `192.168.0.116` or another private IP.
The tunnel route creates the proxied DNS record for the public hostname.

## 2. Create the tunnel

In Cloudflare, open **Networking → Tunnels** (some accounts show this under
Cloudflare One **Networks → Connectors / Tunnels**). Create a **cloudflared**
tunnel named `ukladen-home` and choose **Docker** for the connector instructions.
Copy only the token following `--token` from the displayed install command.
Do not run that command separately: Compose manages the connector.

Create a **Published application** route with:

| Field | Value |
| --- | --- |
| Subdomain | Empty |
| Domain | `ukladen.app` |
| Path | Empty |
| Service type | `HTTP` |
| Service URL | `traefik:80` |

Leave the HTTP Host Header override unset; Traefik matches `ukladen.app`.
Do not use `localhost:8080`: inside this connector, localhost is the connector
container. Remove only conflicting A/AAAA/CNAME records for the root web hostname
if Cloudflare reports an existing record. Do not remove email records.
Cloudflare Access is optional and is separate from Ukladen authentication.

## 3. Configure the application

Use Docker Engine with Compose **2.24.4 or newer**. The overlay uses `!reset` and
`!override` to remove every host port and replace development settings.
Run from the repository root:

```bash
if [ ! -e .env.home ]; then
  (umask 077; cp .env.home.example .env.home)
fi
chmod 600 .env.home
```

Edit `.env.home` locally. Set `CLOUDFLARE_TUNNEL_TOKEN` to the token, and copy
your working PostgreSQL, S3 and SMTP credentials from `.env`. Never paste these
credentials in chat or commit them. The API, worker, Beat and migrations read
`.env.home`; `.env` remains the development configuration.

This deployment reuses the `ukladen` Compose project and its existing PostgreSQL
and SeaweedFS volumes. Existing accounts remain in the same database. Switching
profiles recreates containers and causes a short interruption. Do not run both
profiles at once. Do not run `down --volumes`.

Before public activation, replace development/default database and storage
credentials. If PostgreSQL data already exists, changing `POSTGRES_PASSWORD` in
an env file does **not** rotate its database role. Use the interactive `\password`
command to avoid putting the new password into shell history:

```bash
docker compose exec postgres sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Inside psql run `\password`, enter the new password twice, then `\q`. Update
`POSTGRES_PASSWORD` in both private env files with that same value. Generate a
URL-safe password (for example `openssl rand -hex 32`); the Compose database URL
interpolates it without percent encoding. Update development `DATABASE_URL` too.
For a fresh database, simply set the strong password before its first startup.
Keep a backup before credential changes or migrations. Storage credentials must
also be strong and consistent with the credentials in the existing SeaweedFS
installation; do not assume changing env variables rotates persisted credentials.

The example sets Secure `__Host-` cookies, the exact allowed origin
`https://ukladen.app`, and verification links at
`https://ukladen.app/auth/verify-email`. Copy all your existing SMTP settings,
including port/security and username/password. Cloudflare Tunnel does not send
email. If Google login is enabled, register the public callback
`https://ukladen.app/api/v1/auth/google/callback` with Google and configure all
Google settings together; otherwise leave them commented out.

## 4. Start and verify

Define this convenience function in Bash, then validate and start:

```bash
home_compose() {
  docker compose --env-file .env.home -f docker-compose.yml -f docker-compose.home.yml "$@"
}
home_compose config --quiet
home_compose up --build --detach --wait --wait-timeout 300
home_compose ps
```

`cloudflared` must report **healthy**, and the Cloudflare dashboard must show the
tunnel connected. Its readiness probe checks at least one active edge connection;
it does not prove that domain routing or the edge certificate works.
Check from a phone on mobile data, then from the PC:

```bash
curl --fail https://ukladen.app/health
curl --fail https://ukladen.app/api/health/ready
```

Open `https://ukladen.app`. For auth API tests, follow
[the email end-to-end guide](../development/auth-email.md), changing `AUTH_BASE`
and `Origin` to `https://ukladen.app`. Get a new CSRF token and cookies on this
origin; localhost cookies do not transfer. Request a fresh verification email and
open its link. Reset email still contains a token for the existing reset API.
Never put these tokens into query strings. Avoid Cloudflare cache-everything rules
for `/api/*` or `/auth/*`; preserve the application's no-store responses.

Traefik accepts forwarded headers only from the connector at `172.30.0.2`.
Uvicorn trusts the Traefik (`172.30.0.3`) and connector (`172.30.0.2`) hops in the
forwarded chain, preserving real client addresses for rate limiting. These static
addresses live in the `edge` network, `172.30.0.0/24`; dynamic container addresses
are allocated only from `172.30.0.128/25` so they cannot collide with proxy addresses.
If this subnet conflicts with a LAN/VPN/Docker network on another
host, change the subnet and both trusted/static addresses together before startup.
Neither the API nor Traefik publishes a host port. Traefik access logging is off;
keep cloudflared at its default info level, since debug logging can expose auth data.

For diagnostics, use `home_compose ps` and normal-level service logs. Do not share
resolved `docker compose config`, `docker inspect`, env files or debug logs:
they can contain secrets. If the connector cannot connect, allow outbound DNS and
Cloudflare Tunnel TCP/UDP 7844; no inbound firewall opening is needed. HTTP 502
usually means the connector cannot reach `http://traefik:80`; Cloudflare 1033
usually means no active tunnel connection. DNS/certificate failures require checking
the zone activation, route and certificate status first.

## 5. Keep the PC available and preserve data

Enable Docker Engine at boot with `sudo systemctl enable --now docker`.
All long-running services already use `restart: unless-stopped`; manually stopped
containers stay stopped after reboot. `migrate` runs only during an explicit
Compose startup/update, not as a long-running daemon. Do not depend on Docker
Desktop requiring a user login. Disable automatic suspend while plugged in through
the desktop's Power settings, and keep the PC powered with a stable connection.
Reboot once when convenient and repeat the external health checks; this has not
been verified merely by checking that systemd enables Docker.

Keep the operating system supported and updated before exposing the application.
The inspected host identifies itself as Fedora 42 with `SUPPORT_END=2026-05-27`;
it needs an OS upgrade before public hosting. An OS upgrade/reboot is not performed
by adding this configuration.

PostgreSQL and SeaweedFS data persist in named volumes, but persistence is not a
backup. Before deployment/update, make a database dump (contains private user data):

```bash
mkdir -p backups
chmod 700 backups
umask 077
home_compose exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "backups/ukladen-$(date +%Y%m%d-%H%M%S).dump"
```

Copy backups to a separate disk and test restore in an isolated database. Future
uploaded files also require a consistent SeaweedFS backup; copying a live storage
volume is not a consistent backup. Automated backups and production object-storage
selection are not implemented. Redis remains ephemeral; restarting/recreating it
can lose queued mail. The existing email implementation has no durable outbox.
This single-PC setup has no redundancy: power, internet or hardware failure makes
the website unavailable.

To update, back up first, update the checkout, then rerun the same home Compose
command with `up --build --detach --wait --wait-timeout 300`.
To return to local development, run `home_compose down` (without `--volumes`),
then `docker compose up --build --detach --wait --wait-timeout 180`.
This disconnects the public tunnel while retaining application data.

References: [domain activation](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/),
[remotely managed tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/),
[token configuration](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/),
[Compose merge behavior](https://docs.docker.com/reference/compose-file/merge/),
[HTTPS for .app](https://www.registry.google/domains/app/).
