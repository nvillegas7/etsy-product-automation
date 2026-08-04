#!/usr/bin/env bash
# One-shot: expose the Product Studio dashboard on the internet through the
# SAME Cloudflare account/zone as the castlefight game, WITHOUT touching the
# game's tunnel.
#
#   internet -> https://planner.castlefight.net  (Cloudflare edge, TLS)
#            -> tunnel "etsy-dashboard"          (own process + LaunchAgent)
#            -> http://localhost:5001            (Flask dashboard)
#
# Idempotent: safe to re-run. Rollback at the bottom of this file.
#
# Prereqs checked below: cloudflared installed, account cert present,
# DASHBOARD_PASSWORD set in .env (the dashboard can publish to Etsy --
# never expose it without auth).

set -euo pipefail

HOSTNAME_FQDN="${1:-planner.castlefight.net}"
TUNNEL_NAME="etsy-dashboard"
CF_DIR="$HOME/.cloudflared"
TUNNEL_CONFIG="$CF_DIR/config-planner.yml"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
TUNNEL_PLIST="$AGENTS/com.paulinecolobong.cloudflared-planner.plist"
DASH_PLIST="$AGENTS/com.paulinecolobong.etsy-dashboard.plist"

echo "== Preflight =========================================================="
command -v cloudflared >/dev/null || { echo "FATAL: cloudflared not installed"; exit 1; }
[ -f "$CF_DIR/cert.pem" ] || { echo "FATAL: $CF_DIR/cert.pem missing (cloudflared tunnel login)"; exit 1; }
grep -q "^DASHBOARD_PASSWORD=." "$REPO/.env" || {
  echo "FATAL: DASHBOARD_PASSWORD not set in $REPO/.env -- refusing to expose an unauthenticated dashboard."; exit 1; }
echo "ok: cloudflared, account cert, dashboard password all present"

echo "== 1/5 Tunnel object =================================================="
if cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$TUNNEL_NAME"; then
  echo "ok: tunnel '$TUNNEL_NAME' already exists"
else
  cloudflared tunnel create "$TUNNEL_NAME"
fi
TUNNEL_ID="$(cloudflared tunnel list 2>/dev/null | awk -v n="$TUNNEL_NAME" '$2==n {print $1}')"
[ -n "$TUNNEL_ID" ] || { echo "FATAL: could not resolve tunnel id"; exit 1; }
echo "tunnel id: $TUNNEL_ID"

echo "== 2/5 Tunnel config (separate file; the game's config.yml is untouched)"
cat > "$TUNNEL_CONFIG" <<EOF
# Product Studio dashboard tunnel -- managed by scripts/setup_remote_dashboard.sh
tunnel: $TUNNEL_ID
credentials-file: $CF_DIR/$TUNNEL_ID.json

ingress:
  - hostname: $HOSTNAME_FQDN
    service: http://localhost:5001
  - service: http_status:404
EOF
echo "wrote $TUNNEL_CONFIG"

echo "== 3/5 DNS route ======================================================"
# Creates the CNAME $HOSTNAME_FQDN -> $TUNNEL_ID.cfargotunnel.com (proxied).
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME_FQDN" 2>&1 | tail -1 || true

echo "== 4/5 LaunchAgents (survive reboots) ================================="
mkdir -p "$AGENTS"
cat > "$TUNNEL_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.paulinecolobong.cloudflared-planner</string>
  <key>ProgramArguments</key><array>
    <string>$(command -v cloudflared)</string>
    <string>tunnel</string><string>--config</string><string>$TUNNEL_CONFIG</string>
    <string>run</string><string>$TUNNEL_NAME</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/cloudflared-planner.log</string>
  <key>StandardErrorPath</key><string>/tmp/cloudflared-planner.log</string>
</dict></plist>
EOF
cat > "$DASH_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.paulinecolobong.etsy-dashboard</string>
  <key>ProgramArguments</key><array>
    <string>$REPO/.venv/bin/python</string>
    <string>$REPO/scripts/run_dashboard.py</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/etsy-dashboard.log</string>
  <key>StandardErrorPath</key><string>/tmp/etsy-dashboard.log</string>
</dict></plist>
EOF
launchctl unload "$DASH_PLIST" 2>/dev/null || true
launchctl unload "$TUNNEL_PLIST" 2>/dev/null || true
launchctl load "$DASH_PLIST"
launchctl load "$TUNNEL_PLIST"
echo "loaded both agents (dashboard + tunnel)"

echo "== 5/5 Verify ========================================================="
sleep 4
curl -s -o /dev/null -w "local dashboard:   HTTP %{http_code} (401 = auth working)\n" http://localhost:5001/ || true
curl -s -o /dev/null -w "internet (edge):   HTTP %{http_code} (401 = live + auth; 404/530 = DNS still propagating, retry in 1-2 min)\n" "https://$HOSTNAME_FQDN/" || true

cat <<EOF

DONE. Dashboard: https://$HOSTNAME_FQDN  (user 'admin', password: grep DASHBOARD_PASSWORD .env)

STRONGLY RECOMMENDED (2 min): add Cloudflare Access in front --
  one.dash.cloudflare.com -> Zero Trust -> Access -> Applications -> Add
  self-hosted app for $HOSTNAME_FQDN, policy: Allow -> Emails -> your email.
  Then every visit needs an email OTP BEFORE reaching the dashboard;
  basic auth stays as a second layer.

ROLLBACK (full):
  launchctl unload "$TUNNEL_PLIST" "$DASH_PLIST"; rm "$TUNNEL_PLIST" "$DASH_PLIST"
  cloudflared tunnel route dns --overwrite-dns is not needed; delete the
  $HOSTNAME_FQDN CNAME in the Cloudflare DNS dashboard, then:
  cloudflared tunnel delete $TUNNEL_NAME
EOF
