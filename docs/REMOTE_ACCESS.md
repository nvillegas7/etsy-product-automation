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
   `DASHBOARD_PASSWORD` in `.env`. TLS is terminated at Cloudflare's edge;
   the tunnel leg is encrypted by cloudflared.
2. **Cloudflare Access (strongly recommended, ~2 min, free tier):**
   Zero Trust → Access → Applications → Add self-hosted app for the
   hostname, policy Allow → Emails → your email. Every visit then requires
   an email OTP at the edge *before* any request reaches the Flask app.
3. Flask runs with `debug=False`; the tunnel's catch-all returns 404.

## Rollback

Printed at the end of the setup script: unload/remove the two LaunchAgents,
delete the DNS CNAME in the Cloudflare dashboard, `cloudflared tunnel delete
etsy-dashboard`. The game's tunnel is unaffected throughout.

## Note on the game tunnel

The `castlefight` tunnel currently runs as a **foreground process** (started
manually; no LaunchAgent) — it will not survive a reboot. The same plist
pattern used here would fix that; see `scripts/setup_remote_dashboard.sh`
step 4.
