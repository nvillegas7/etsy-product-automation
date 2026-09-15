# Remote dashboard access (Cloudflare Tunnel)

The Product Studio dashboard is LAN-only by default. For internet access it
reuses the **same Cloudflare account + `castlefight.net` zone** as the
`paulinecolobong/game` project — via a **separate tunnel**, so the game's
`castlefight` tunnel (`nakama.castlefight.net`, `~/.cloudflared/config.yml`)
is never touched or restarted.

```
internet ──HTTPS──> planner.castlefight.net (Cloudflare edge)
                      └─ tunnel "etsy-dashboard" (~/.cloudflared/config-planner.yml)
                           └─ http://localhost:5001 (Flask dashboard)
```

## Setup / go-live

One command (idempotent):

    bash scripts/setup_remote_dashboard.sh            # planner.castlefight.net
    bash scripts/setup_remote_dashboard.sh other.castlefight.net   # custom name

It refuses to run unless `DASHBOARD_PASSWORD` is set in `.env` (this
dashboard approves + publishes to the live Etsy shop). It creates the tunnel,
writes its own config file, routes DNS, and installs two LaunchAgents
(`com.paulinecolobong.cloudflared-planner`, `com.paulinecolobong.etsy-dashboard`)
so both the tunnel and the dashboard survive reboots. Logs:
`/tmp/cloudflared-planner.log`, `/tmp/etsy-dashboard.log`.

## Security layers

1. **HTTP Basic auth** (enforced): user `admin`, password from
   `DASHBOARD_PASSWORD` in `.env`, compared in constant time. TLS is
   terminated at Cloudflare's edge; the tunnel leg is encrypted by cloudflared.
2. **Brute-force throttle:** 8 failed logins from one client inside 15 min
   → HTTP 429 for that client (`DASHBOARD_AUTH_MAX_FAILURES` /
   `DASHBOARD_AUTH_FAIL_WINDOW` to tune). Behind the tunnel the client is
   taken from `CF-Connecting-IP`, trusted only when the peer is loopback.
3. **CSRF / same-origin writes:** every POST (approve, reject, publish,
   edit, generate) must carry an `Origin`/`Referer` matching the host, and
   Fetch-Metadata `cross-site` requests are refused — a hostile page cannot
   ride the reviewer's cached credentials into a paid publish.
4. **Headers:** `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy:
   same-origin`, `frame-ancestors 'none'`, HSTS, `Cache-Control: no-store`.
5. **Session key** from `DASHBOARD_SECRET_KEY` (else random per process —
   never the old predictable default). Served by **waitress**, not the
   Werkzeug dev server; `debug=False`; the tunnel's catch-all returns 404.
6. **Cloudflare Access (strongly recommended, ~2 min, free tier):**
   Zero Trust → Access → Applications → Add self-hosted app for the
   hostname, policy Allow → Emails → your email. Every visit then requires
   an email OTP at the edge *before* any request reaches the app. Basic
   auth stays as the second layer.

The setup script also retires any hand-started `run_dashboard.py` process
so the LaunchAgent serves the current code (a dashboard started 7/7 kept
generating products with pre-7/10 code until September).

## Rollback

Printed at the end of the setup script: unload/remove the two LaunchAgents,
delete the DNS CNAME in the Cloudflare dashboard, `cloudflared tunnel delete
etsy-dashboard`. The game's tunnel is unaffected throughout.

## Note on the game tunnel

The `castlefight` tunnel currently runs as a **foreground process** (started
manually; no LaunchAgent) — it will not survive a reboot. The same plist
pattern used here would fix that; see `scripts/setup_remote_dashboard.sh`
step 4.
