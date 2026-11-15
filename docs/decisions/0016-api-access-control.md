# ADR-0016: API binds to localhost; token-authenticated POST; token for reads on LAN

Status: accepted (owner approved 2026-11-15) · Pipeline 3.1.0

## Problem

`parkinsense-live` bound `0.0.0.0:8000` with no authentication, so anyone on the network could read live physiological
data and start/stop sessions (the audit's WP-03). The launch scripts already bound `127.0.0.1`.

## Decision

* Default `--host 127.0.0.1`. LAN exposure is an explicit opt-in (`--host 0.0.0.0`), documented in
  `docs/software/DASHBOARD_AND_API.md`, and logs a warning.
* `POST /session/start|stop` require `X-ParkinSense-Token`; constant-time comparison; no configured token → 403.
* A non-loopback bind additionally requires the token for `/metrics`, `/live`, `/session` (`/health` stays open for
  liveness checks). This goes one step beyond "authenticated POST" because an opened LAN port would otherwise leak data.
* Token: `--token` > `$PARKINSENSE_TOKEN` > token file (`$PARKINSENSE_TOKEN_FILE`, default `~/.parkinsense/api_token`,
  mode 0600, auto-created by the server). The dashboard client reads the same sources and never creates the file.

## Consequences

* Breaking for LAN/script clients: add the header, or the phone app must be given the token. No in-repo mobile app exists.
* No TLS; the token is a shared secret in clear text on the LAN. Not a substitute for a trusted network.
* No schema, capture or algorithm change.

Evidence: automated tests (`tests/integration/test_api_auth.py`); not exercised from a second device.
