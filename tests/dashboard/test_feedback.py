"""Reviewer-feedback collection: comments captured on every decision,
required on rejection, kept as an append-only history, and surfaced on a
feedback page for later analysis."""

from src.storage.models import ProductState
from src.storage.repository import ProductRepository, ReviewEventRepository


def _events(session_factory, product_id):
    s = session_factory()
    try:
        return ReviewEventRepository(s).list_for_product(product_id)
    finally:
        s.close()


def _state(session_factory, product_id):
    s = session_factory()
    try:
        return ProductRepository(s).get(product_id).state
    finally:
        s.close()


def test_reject_requires_a_comment(dashboard):
    client, ids, sf = dashboard
    pid = ids["pending"]
    resp = client.post(f"/product/{pid}/reject", data={}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Please add a comment" in resp.data
    assert _state(sf, pid) == ProductState.REVIEW_PENDING  # unchanged
    assert _events(sf, pid) == []  # nothing logged


def test_reject_with_comment_logs_structured_event(dashboard):
    client, ids, sf = dashboard
    pid = ids["pending"]
    client.post(
        f"/product/{pid}/reject",
        data={"note": "Cover motif looks generic", "reason": "design"},
        follow_redirects=True,
    )
    assert _state(sf, pid) == ProductState.REJECTED
    evs = _events(sf, pid)
    assert len(evs) == 1
    ev = evs[0]
    assert ev.decision == "rejected"
    assert ev.comment == "Cover motif looks generic"
    assert ev.reason == "design"
    assert ev.product_type == "planner"
    assert ev.params_snapshot  # attribute snapshot captured for analysis


def test_approve_logs_event(dashboard):
    client, ids, sf = dashboard
    pid = ids["pending"]
    client.post(
        f"/product/{pid}/approve", data={"note": "clean"}, follow_redirects=True
    )
    assert _state(sf, pid) == ProductState.APPROVED
    evs = _events(sf, pid)
    assert len(evs) == 1 and evs[0].decision == "approved"


def test_history_is_append_only_across_cycles(dashboard):
    client, ids, sf = dashboard
    pid = ids["pending"]
    client.post(f"/product/{pid}/reject", data={"note": "first reject"}, follow_redirects=True)
    client.post(f"/product/{pid}/re-review", data={}, follow_redirects=True)
    client.post(f"/product/{pid}/reject", data={"note": "second reject"}, follow_redirects=True)
    evs = _events(sf, pid)
    assert len(evs) == 3
    comments = [e.comment for e in evs if e.comment]
    assert "first reject" in comments and "second reject" in comments


def test_detail_shows_review_history(dashboard):
    client, ids, sf = dashboard
    pid = ids["pending"]
    client.post(
        f"/product/{pid}/reject", data={"note": "history-marker-xyz"}, follow_redirects=True
    )
    resp = client.get(f"/product/{pid}")
    assert b"Review history" in resp.data
    assert b"history-marker-xyz" in resp.data


def test_feedback_page_collects_rejections(dashboard):
    client, ids, sf = dashboard
    pid = ids["pending"]
    client.post(
        f"/product/{pid}/reject",
        data={"note": "reject-marker-abc", "reason": "quality"},
        follow_redirects=True,
    )
    resp = client.get("/feedback")
    assert resp.status_code == 200
    assert b"reject-marker-abc" in resp.data
    # explicit rejected filter also works
    assert b"reject-marker-abc" in client.get("/feedback?decision=rejected").data


def test_nav_links_to_feedback(dashboard):
    client, ids, sf = dashboard
    assert b"/feedback" in client.get("/").data
