"""Run the Product Studio manual-approval dashboard.

Usage: python scripts/run_dashboard.py

Every generated product waits in REVIEW_PENDING until you approve or
reject it here. Only approved products can be published to Etsy.
"""

import os
import socket
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import yaml

from src.dashboard.app import PROJECT_ROOT, create_app


def _lan_ip() -> str:
    """Best-effort LAN IP of this machine (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(fh) or {}

    dashboard_cfg = config.get("dashboard", {}) or {}
    host = dashboard_cfg.get("host", "127.0.0.1")
    port = int(dashboard_cfg.get("port", 5001))
    protected = bool(os.getenv("DASHBOARD_PASSWORD", "").strip())

    app = create_app(config)

    print()
    if host in ("0.0.0.0", "::"):
        print("  Product Studio is running. Open on any device on this WiFi:")
        print(f"    -> http://{_lan_ip()}:{port}   (this computer's LAN address)")
        print(f"    -> http://localhost:{port}      (this computer)")
        print("  LAN-only: your router blocks outside access unless you port-forward.")
    else:
        print(f"  Product Studio is running -> http://{host}:{port}")
    if protected:
        user = os.getenv("DASHBOARD_USER", "admin").strip() or "admin"
        print(f"  Login required (user '{user}', password from DASHBOARD_PASSWORD).")
    else:
        print("  No password set. Set DASHBOARD_PASSWORD in .env to require a login.")
    print("  Review pending products, approve or reject, then publish.")
    print("  Press Ctrl+C to stop.")
    print()

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
