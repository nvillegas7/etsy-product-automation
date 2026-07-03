"""ReviewEventRepository: append-only review feedback log."""

import pytest

from src.storage.database import get_session_factory, init_db, reset_engine
from src.storage.repository import ReviewEventRepository


@pytest.fixture()
def session_factory(tmp_path):
    reset_engine()
    init_db(f"sqlite:///{tmp_path}/t.db")
    sf = get_session_factory()
    yield sf
    reset_engine()


def test_add_and_history_is_append_only(session_factory):
    s = session_factory()
    try:
        repo = ReviewEventRepository(s)
        repo.add(1, "rejected", product_type="planner", reason="design", comment="c1")
        repo.add(1, "re_review", comment=None)
        repo.add(1, "rejected", reason="quality", comment="c2")
        repo.add(2, "approved", comment="ok")

        hist = repo.list_for_product(1)
        assert len(hist) == 3  # not overwritten
        # newest first
        assert hist[0].comment == "c2"
        assert [e.decision for e in hist] == ["rejected", "re_review", "rejected"]
    finally:
        s.close()


def test_list_all_filter_and_counts(session_factory):
    s = session_factory()
    try:
        repo = ReviewEventRepository(s)
        repo.add(1, "rejected", comment="a")
        repo.add(2, "rejected", comment="b")
        repo.add(3, "approved", comment="c")

        rejections = repo.list_all(decision="rejected")
        assert len(rejections) == 2
        assert {e.comment for e in rejections} == {"a", "b"}

        assert repo.list_all() and len(repo.list_all()) == 3
        assert repo.counts_by_decision() == {"rejected": 2, "approved": 1}
    finally:
        s.close()
