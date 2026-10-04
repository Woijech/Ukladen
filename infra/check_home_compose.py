"""Check the resolved home Compose model: pipe `config --format json` into this."""

import json
import sys
from ipaddress import ip_address, ip_network

model = json.load(sys.stdin)
services = model["services"]
edge = model["networks"]["edge"]["ipam"]["config"][0]
assert edge["subnet"] == "172.30.0.0/24"
for address in ("172.30.0.2", "172.30.0.3"):
    assert ip_address(address) not in ip_network(edge["ip_range"]), "Proxy address not reserved"
assert all(not service.get("ports") for service in services.values()), "Host port exposed"
for name in ("api", "worker", "beat", "migrate"):
    env = services[name]["environment"]
    assert env["CLOUDFLARE_TUNNEL_TOKEN"] == ""
    assert env["AUTH_COOKIE_SECURE"] == "true"
    assert json.loads(env["AUTH_ALLOWED_ORIGINS"]) == ["https://ukladen.app"]
    assert env["AUTH_EMAIL_VERIFICATION_URL"] == "https://ukladen.app/auth/verify-email"
    assert env["AUTH_SESSION_COOKIE_NAME"] == "__Host-ukladen_session"

proxy = services["traefik"]
assert "--accesslog=false" in proxy["command"]
assert "--entrypoints.web.forwardedheaders.trustedips=172.30.0.2/32" in proxy["command"]
assert proxy["networks"]["edge"]["ipv4_address"] == "172.30.0.3"
assert set(proxy["networks"]) == {"edge"}
assert services["api"]["environment"]["FORWARDED_ALLOW_IPS"] == "172.30.0.3,172.30.0.2"
tunnel = services["cloudflared"]
assert tunnel["networks"]["edge"]["ipv4_address"] == "172.30.0.2"
assert "--token" not in tunnel["command"], "Tunnel secret must not be a CLI argument"
assert tunnel["environment"]["TUNNEL_TOKEN"]
print("Home Compose exposure, secrets and proxy trust checks passed.")
