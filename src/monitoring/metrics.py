"""Pipeline metrics tracking."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.storage.models import PipelineRun, Product, ProductState


def _utcnow() -> datetime:
    """Naive UTC now — matches the naive UTC timestamps SQLite stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PipelineMetrics:
    def __init__(self, session: Session):
        self.session = session

    def products_today(self) -> int:
        today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.execute(
            select(func.count(Product.id)).where(
                Product.state == ProductState.PUBLISHED,
                Product.created_at >= today_start,
            )
        ).scalar_one()

    def generated_today(self) -> int:
        """Products created today in any state — used for the daily quota."""
        today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.execute(
            select(func.count(Product.id)).where(
                Product.created_at >= today_start,
            )
        ).scalar_one()

    def count_by_state(self) -> dict[str, int]:
        """Product counts keyed by state value, for dashboards."""
        rows = self.session.execute(
            select(Product.state, func.count(Product.id)).group_by(Product.state)
        ).all()
        return {state.value: count for state, count in rows}

    def products_this_week(self) -> int:
        week_start = _utcnow() - timedelta(days=7)
        return self.session.execute(
            select(func.count(Product.id)).where(
                Product.state == ProductState.PUBLISHED,
                Product.created_at >= week_start,
            )
        ).scalar_one()

    def failed_today(self) -> int:
        today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.execute(
            select(func.count(Product.id)).where(
                Product.state == ProductState.FAILED,
                Product.created_at >= today_start,
            )
        ).scalar_one()

    def pipeline_runs_today(self) -> int:
        today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.execute(
            select(func.count(PipelineRun.id)).where(
                PipelineRun.started_at >= today_start,
            )
        ).scalar_one()

    def summary(self) -> dict:
        return {
            "products_today": self.products_today(),
            "products_this_week": self.products_this_week(),
            "failed_today": self.failed_today(),
            "pipeline_runs_today": self.pipeline_runs_today(),
        }
