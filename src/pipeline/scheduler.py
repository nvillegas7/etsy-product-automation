"""APScheduler-based cadence manager for the pipeline.

Run directly::

    python -m src.pipeline.scheduler

This loads config, initialises the database, creates the orchestrator,
and starts a blocking scheduler that fires ``run_once()`` at the
configured cadence.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

if TYPE_CHECKING:
    from src.pipeline.orchestrator import PipelineOrchestrator

logger = structlog.get_logger()

# Project root (three levels up: src/pipeline/scheduler.py -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class PipelineScheduler:
    """Schedule recurring pipeline cycles using APScheduler.

    Parameters
    ----------
    orchestrator : PipelineOrchestrator
        The orchestrator instance whose ``run_once()`` will be called
        on each tick.
    config : dict
        Parsed ``config.yaml`` contents.  Uses
        ``config["pipeline"]["cadence_seconds"]`` for the interval.
    """

    def __init__(self, orchestrator: "PipelineOrchestrator", config: dict):
        self.orchestrator = orchestrator
        self.config = config
        self._scheduler = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create and start the blocking scheduler.

        * Adds an interval job that calls ``orchestrator.run_once()``.
        * Registers SIGINT / SIGTERM handlers for graceful shutdown.
        * Runs an immediate first cycle before entering the schedule loop.
        """
        from apscheduler.schedulers.blocking import BlockingScheduler

        cadence = self.config.get("pipeline", {}).get("cadence_seconds", 3600)

        self._scheduler = BlockingScheduler()

        # Interval job
        self._scheduler.add_job(
            self._safe_run,
            trigger="interval",
            seconds=cadence,
            id="pipeline_cycle",
            name="Pipeline cycle",
            max_instances=1,
            coalesce=True,
        )

        # Immediate startup job (runs once, right away)
        self._scheduler.add_job(
            self._safe_run,
            trigger="date",  # fires immediately (default run_date=now)
            id="pipeline_startup",
            name="Pipeline startup run",
        )

        # Graceful shutdown on signals
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info(
            "scheduler_starting",
            cadence_seconds=cadence,
            max_products_per_day=self.config.get("pipeline", {}).get(
                "max_products_per_day", 10
            ),
        )

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("scheduler_interrupted")
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler is not None and self._scheduler.running:
            logger.info("scheduler_stopping")
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _safe_run(self) -> None:
        """Wrap ``run_once()`` so that exceptions never crash the scheduler."""
        try:
            logger.info("pipeline_cycle_starting")
            product = self.orchestrator.run_once()
            if product is not None:
                logger.info(
                    "pipeline_cycle_finished",
                    product_id=product.id,
                    state=product.state.value,
                )
            else:
                logger.info("pipeline_cycle_finished", product_id=None)
        except Exception as exc:
            logger.error(
                "pipeline_cycle_exception",
                error=str(exc),
                exc_info=True,
            )

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info("signal_received", signal=sig_name)
        self.stop()


# ======================================================================
# Module entry point: python -m src.pipeline.scheduler
# ======================================================================


def _load_config() -> dict:
    """Load the main config.yaml."""
    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def main() -> None:
    """Entry point for ``python -m src.pipeline.scheduler``."""
    # Load .env if python-dotenv is available
    try:
        from dotenv import load_dotenv

        env_path = _PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded .env from {env_path}")
    except ImportError:
        pass

    # Setup structured logging
    from src.monitoring.logger import setup_logging

    setup_logging()

    # Load config
    config = _load_config()
    logger.info("config_loaded", pipeline=config.get("pipeline"))

    # Initialise database
    from src.storage.database import get_session_factory, init_db

    db_path = config.get("paths", {}).get("database", "data/planner.db")
    database_url = f"sqlite:///{db_path}"
    init_db(database_url)
    session_factory = get_session_factory(database_url)
    logger.info("database_initialized", url=database_url)

    # Create orchestrator
    from src.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(config=config, session_factory=session_factory)

    # Start scheduler
    scheduler = PipelineScheduler(orchestrator=orchestrator, config=config)
    scheduler.start()


if __name__ == "__main__":
    main()
