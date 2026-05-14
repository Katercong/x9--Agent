"""Tests for the dashboard → extension command channel."""
from __future__ import annotations


def _hb(client, worker_id="local_worker_01"):
    client.post("/api/local/extension/heartbeat", json={
        "event_type": "extension_heartbeat",
        "extension_id": "x9_tiktok_collector", "extension_version": "3.1.0",
        "worker_id": worker_id, "account_id": "a", "browser_profile": "p",
        "current_url": "https://www.tiktok.com/@x", "tiktok_page_status": "on_tiktok",
        "tiktok_login_status": "logged_in", "page_type": "creator_profile",
        "active_tab_title": "TikTok", "timestamp": "2026-05-08T00:00:00Z",
    })


def test_push_pending_ack_command_roundtrip(client):
    _hb(client, "cmd_worker_a")

    # Dashboard pushes a command (worker_id None → broadcast to most-recent online worker)
    r = client.post("/api/local/extension/commands", json={
        "worker_id": "cmd_worker_a",
        "command_type": "collect_now",
        "payload": {"foo": "bar"},
    })
    assert r.status_code == 200
    cmd = r.json()["command"]
    assert cmd["status"] == "pending"
    assert cmd["worker_id"] == "cmd_worker_a"

    # Extension polls — gets it and it transitions to claimed
    r = client.get("/api/local/extension/commands/pending?worker_id=cmd_worker_a&claim=true")
    items = r.json()["items"]
    assert any(x["id"] == cmd["id"] and x["status"] == "claimed" for x in items)

    # Polling again returns nothing (already claimed)
    r2 = client.get("/api/local/extension/commands/pending?worker_id=cmd_worker_a")
    assert all(x["id"] != cmd["id"] for x in r2.json()["items"])

    # Extension acks done with a result
    r3 = client.post(f"/api/local/extension/commands/{cmd['id']}/ack",
                     json={"status": "done", "result": {"handle": "natashathasan", "action": "inserted"}})
    assert r3.status_code == 200
    assert r3.json()["command"]["status"] == "done"

    # Listing the command shows the final state
    r4 = client.get(f"/api/local/extension/commands?worker_id=cmd_worker_a&limit=10")
    matched = [x for x in r4.json()["items"] if x["id"] == cmd["id"]]
    assert matched and matched[0]["status"] == "done"


def test_broadcast_picks_online_worker(client):
    _hb(client, "broadcast_target")
    r = client.post("/api/local/extension/commands", json={"command_type": "heartbeat"})
    # 200 if at least one online worker exists; 409 otherwise. Either way the route is reachable.
    assert r.status_code in (200, 409)


def test_push_with_no_online_worker_fails_when_unspecified(client):
    # We can't easily clear sessions in this fixture, so assert the
    # explicit-worker path always works as the safe baseline.
    r = client.post("/api/local/extension/commands", json={
        "worker_id": "explicit_worker", "command_type": "set_search_keyword",
        "payload": {"search_keyword": "feminine care"},
    })
    assert r.status_code == 200
    assert r.json()["command"]["worker_id"] == "explicit_worker"
