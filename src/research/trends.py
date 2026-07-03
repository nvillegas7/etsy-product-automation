"""Google Trends client with caching and rate limiting via pytrends."""

import time
from datetime import datetime

import structlog

from src.storage.repository import TrendCacheRepository
from src.utils.retry import retry_with_backoff

logger = structlog.get_logger()

# Guard pytrends import so the module is importable even without it installed
try:
    from pytrends.request import TrendReq
    from pytrends.exceptions import TooManyRequestsError, ResponseError

    _PYTRENDS_AVAILABLE = True
except ImportError:
    _PYTRENDS_AVAILABLE = False
    TrendReq = None  # type: ignore[assignment,misc]
    TooManyRequestsError = Exception  # type: ignore[assignment,misc]
    ResponseError = Exception  # type: ignore[assignment,misc]


class TrendsClient:
    """Wraps pytrends with SQLite caching and polite rate limiting.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Database session used for the trend cache.
    cache_ttl_hours : int
        How many hours a cached trend result stays valid (default 24).
    request_delay : int | float
        Minimum seconds to wait between live pytrends requests (default 60).
    """

    def __init__(
        self,
        session,
        cache_ttl_hours: int = 24,
        request_delay: int | float = 60,
    ):
        self._session = session
        self._cache_repo = TrendCacheRepository(session)
        self._cache_ttl_hours = cache_ttl_hours
        self._request_delay = request_delay
        self._last_request_at: float | None = None

        # Lazy-initialised on first real request
        self._pytrends = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_pytrends(self) -> None:
        """Initialise the TrendReq object once, on demand."""
        if not _PYTRENDS_AVAILABLE:
            raise RuntimeError(
                "pytrends is not installed. Install it with: pip install pytrends"
            )
        if self._pytrends is None:
            self._pytrends = TrendReq(hl="en-US", tz=360)

    def _wait_for_rate_limit(self) -> None:
        """Sleep until enough time has passed since the last request."""
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            remaining = self._request_delay - elapsed
            if remaining > 0:
                logger.info(
                    "trends_rate_limit_wait",
                    wait_seconds=round(remaining, 1),
                )
                time.sleep(remaining)

    def _record_request(self) -> None:
        self._last_request_at = time.monotonic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_interest(
        self,
        keyword: str,
        timeframe: str = "today 12-m",
    ) -> dict:
        """Return interest-over-time data for *keyword*.

        Returns a dict with keys:
            ``dates``  - list of ISO-formatted date strings
            ``values`` - list of int interest values (0-100)

        Results are cached in SQLite; a live request is only made when the
        cache is missing or expired.
        """
        # 1. Try the cache first
        cached = self._cache_repo.get_cached(keyword, ttl_hours=self._cache_ttl_hours)
        if cached is not None:
            logger.debug("trends_cache_hit", keyword=keyword)
            return cached

        # 2. Live fetch
        logger.info("trends_fetching", keyword=keyword, timeframe=timeframe)
        data = self._fetch_interest(keyword, timeframe)

        # 3. Persist to cache
        score = self.calculate_trend_direction(data) if data["values"] else None
        self._cache_repo.save(keyword=keyword, trend_data=data, score=score)

        return data

    @retry_with_backoff(
        max_retries=2,
        base_delay=5.0,
        max_delay=120.0,
        exceptions=(Exception,),
    )
    def _fetch_interest(self, keyword: str, timeframe: str) -> dict:
        """Perform the actual pytrends API call (retried on transient errors)."""
        self._ensure_pytrends()
        self._wait_for_rate_limit()

        try:
            self._pytrends.build_payload([keyword], timeframe=timeframe, geo="US")
            df = self._pytrends.interest_over_time()
            self._record_request()
        except (TooManyRequestsError, ResponseError) as exc:
            self._record_request()
            logger.warning("trends_api_error", keyword=keyword, error=str(exc))
            raise
        except Exception as exc:
            self._record_request()
            logger.error("trends_unexpected_error", keyword=keyword, error=str(exc))
            raise

        if df is None or df.empty or keyword not in df.columns:
            logger.warning("trends_no_data", keyword=keyword)
            return {"dates": [], "values": []}

        # Drop the isPartial column if present
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])

        dates = [d.isoformat() for d in df.index]
        values = df[keyword].tolist()

        return {"dates": dates, "values": values}

    def get_related_queries(self, keyword: str) -> list[str]:
        """Return a flat list of related-query strings for *keyword*.

        Returns an empty list when pytrends is unavailable or no data is
        returned.
        """
        cache_key = f"__related__{keyword}"
        cached = self._cache_repo.get_cached(cache_key, ttl_hours=self._cache_ttl_hours)
        if cached is not None:
            logger.debug("related_cache_hit", keyword=keyword)
            return cached.get("queries", [])

        logger.info("related_fetching", keyword=keyword)
        queries = self._fetch_related_queries(keyword)

        # Cache the result
        self._cache_repo.save(keyword=cache_key, trend_data={"queries": queries})

        return queries

    @retry_with_backoff(
        max_retries=2,
        base_delay=5.0,
        max_delay=120.0,
        exceptions=(Exception,),
    )
    def _fetch_related_queries(self, keyword: str) -> list[str]:
        self._ensure_pytrends()
        self._wait_for_rate_limit()

        try:
            self._pytrends.build_payload([keyword], timeframe="today 12-m", geo="US")
            related = self._pytrends.related_queries()
            self._record_request()
        except (TooManyRequestsError, ResponseError) as exc:
            self._record_request()
            logger.warning("related_api_error", keyword=keyword, error=str(exc))
            raise
        except Exception as exc:
            self._record_request()
            logger.error("related_unexpected_error", keyword=keyword, error=str(exc))
            raise

        results: list[str] = []
        if related and keyword in related:
            for relation_type in ("top", "rising"):
                df = related[keyword].get(relation_type)
                if df is not None and not df.empty:
                    results.extend(df["query"].tolist())

        return results

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_trend_direction(interest_data: dict) -> float:
        """Compute a trend direction score in the range ``[-100, 100]``.

        The score compares the average interest of the most recent 3 months
        against the preceding 3 months.  A positive value means the keyword
        is trending upward; negative means it is losing interest.

        If there is insufficient data (fewer than 2 points), returns 0.0.
        """
        values = interest_data.get("values", [])
        if len(values) < 2:
            return 0.0

        # Roughly split into two halves; take last ~quarter vs previous ~quarter
        # With weekly data over 12 months we get ~52 points.
        # "3 months" = ~13 data points for weekly data.
        quarter_len = max(len(values) // 4, 1)

        recent = values[-quarter_len:]
        previous = values[-(2 * quarter_len) : -quarter_len]

        if not previous or not recent:
            return 0.0

        avg_recent = sum(recent) / len(recent)
        avg_previous = sum(previous) / len(previous)

        if avg_previous == 0:
            return 100.0 if avg_recent > 0 else 0.0

        # Percentage change, clamped to [-100, 100]
        pct_change = ((avg_recent - avg_previous) / avg_previous) * 100
        return max(-100.0, min(100.0, round(pct_change, 2)))
