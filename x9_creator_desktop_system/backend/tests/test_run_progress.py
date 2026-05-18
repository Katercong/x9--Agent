"""Tests for the auto-run progress endpoints."""
from __future__ import annotations

from x9_creator_desktop_system.backend.routers.extension import _as_aware_utc


def _push(client, **patch):
    body = {
        "worker_id": "rp_worker",
        "step": "scanning",
        "running": True,
        "stop_requested": False,
        "started_at": "2026-05-08T08:00:00Z",
        "elapsed_seconds": 12,
        "profiles_visited": 3,
        "profiles_remaining": 27,
        "queue_size": 5,
        "leads_saved": 2,
        "skipped": 1,
        "scrolls_done": 1,
        "rest_breaks": 0,
        "current_handle": "natashathasan",
        "current_action": "Scanning search results for new videos",
        "keyword": "feminine care",
        "settings": {"max_profiles": 30, "max_scrolls": 8, "min_followers": 0, "require_email": False},
        "queue": [{"handle": "a"}, {"handle": "b"}],
        "recent_leads": [{"handle": "natashathasan", "followers": 844500}],
    }
    body.update(patch)
    return client.post("/api/local/extension/run-progress", json=body)


def test_run_progress_upsert_and_read(client):
    r = _push(client)
    assert r.status_code == 200
    assert r.json()["progress"]["worker_id"] == "rp_worker"
    assert r.json()["progress"]["leads_saved"] == 2

    # Update with new counters — same row, latest values
    r2 = _push(client, profiles_visited=5, leads_saved=3, skipped=2)
    assert r2.json()["progress"]["leads_saved"] == 3
    assert r2.json()["progress"]["profiles_visited"] == 5

    # GET by worker_id
    r3 = client.get("/api/local/extension/run-progress?worker_id=rp_worker")
    assert r3.status_code == 200
    assert r3.json()["progress"]["leads_saved"] == 3

    # GET list (no filter) — includes our row
    r4 = client.get("/api/local/extension/run-progress")
    workers = [x["worker_id"] for x in r4.json()["items"]]
    assert "rp_worker" in workers


def test_run_progress_finished_state(client):
    r = _push(client, running=False, step="finished", finished_at="2026-05-08T08:02:30Z",
              profiles_visited=30, profiles_remaining=0, leads_saved=18, skipped=12)
    p = r.json()["progress"]
    assert p["running"] is False
    assert p["step"] == "finished"
    assert p["leads_saved"] == 18
    assert p["finished_at"] is not None


def test_extension_datetime_helper_accepts_legacy_strings():
    parsed = _as_aware_utc("2026-05-08 08:02:30")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.isoformat().startswith("2026-05-08T08:02:30")
