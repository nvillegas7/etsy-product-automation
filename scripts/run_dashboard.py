"""Run the Product Studio manual-approval dashboard.

Usage: python scripts/run_dashboard.py

Every generated product waits in REVIEW_PENDING until you approve or
reject it here. Only approved products can be published to Etsy.
"""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import yaml

from src.dashboard.app import PROJECT_ROOT, create_app


def main() -> None:
    config_path = PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(fh) or {}

    dashboard_cfg = config.get("dashboard", {}) or {}
    host = dashboard_cfg.get("host", "127.0.0.1")
    port = int(dashboard_cfg.get("port", 5001))

    app = create_app(config)

    print()
    print(f"  Product Studio is running -> http://{host}:{port}")
    print("  Review pending products, approve or reject, then publish.")
    print("  Press Ctrl+C to stop.")
    print()

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
