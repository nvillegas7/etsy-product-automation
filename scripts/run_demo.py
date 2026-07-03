"""Demo runner: generate products at a fixed interval.

Each product ends in REVIEW_PENDING — open the dashboard
(scripts/run_dashboard.py) to approve or reject before anything
can reach Etsy. Usage: python scripts/run_demo.py [cycles]
"""

import os
import signal
import sqlite3
import sys
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.monitoring.logger import setup_logging

setup_logging("INFO")

import structlog
import yaml

from src.pipeline.orchestrator import PipelineOrchestrator
from src.storage.database import get_session_factory, init_db, reset_engine

logger = structlog.get_logger()

reset_engine()

with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

init_db()
sf = get_session_factory()
orch = PipelineOrchestrator(config, sf)

cadence = config.get("pipeline", {}).get("cadence_seconds", 60)
max_cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 5
stop = False


def handle_signal(signum, frame):
    global stop
    stop = True
    print("\nStopping gracefully...")


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

print(f"=== Etsy Planner Bot Demo: {max_cycles} products, {cadence}s interval ===")
print()

for cycle in range(1, max_cycles + 1):
    if stop:
        print("Stopped by signal.")
        break

    start = time.time()
    print(f"--- Cycle {cycle}/{max_cycles} ---")
    product = orch.run_once()

    if product:
        elapsed = time.time() - start
        title_short = product.title[:70]
        size_mb = (
            f"{product.file_size_bytes / (1024 * 1024):.2f} MB"
            if product.file_size_bytes
            else "N/A"
        )
        print(f"  Product #{product.id}: {title_short}")
        print(f"  Palette: {product.palette_name} | Size: {size_mb} | Gen time: {elapsed:.1f}s")
        print(f"  PDF: {product.pdf_path}")
    else:
        print(f"  Cycle {cycle} returned None")

    print()

    if cycle < max_cycles and not stop:
        remaining = max(0, cadence - (time.time() - start))
        print(f"  Waiting {remaining:.0f}s until next cycle...")
        end_time = time.time() + remaining
        while time.time() < end_time and not stop:
            time.sleep(1)

print()
print("=" * 60)
print("=== Pipeline Demo Complete ===")
print("=" * 60)
print()

# Summary from DB
db_path = "data/planner.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, product_type, title, palette_name, state, pdf_path FROM products"
    ).fetchall()
    print(f"Total products created: {len(rows)}")
    for r in rows:
        title = r[2][:55] if r[2] else "?"
        print(f"  #{r[0]}: [{r[4]}] {r[1]:12s} {r[3]:20s} | {title}")
    conn.close()
    print("\nNext: review products in the dashboard -> python scripts/run_dashboard.py")

# List output files
pdf_dir = "output/planners"
if os.path.exists(pdf_dir):
    files = sorted(os.listdir(pdf_dir))
    pdf_files = [f for f in files if f.endswith(".pdf")]
    print(f"\nGenerated {len(pdf_files)} PDFs in {pdf_dir}/:")
    for f in pdf_files:
        size = os.path.getsize(os.path.join(pdf_dir, f))
        print(f"  {f}  ({size / (1024 * 1024):.2f} MB)")

mockup_dir = "output/mockups"
if os.path.exists(mockup_dir):
    mocks = sorted(os.listdir(mockup_dir))
    mock_files = [f for f in mocks if f.endswith(".png")]
    if mock_files:
        print(f"\nGenerated {len(mock_files)} mockup images in {mockup_dir}/")
