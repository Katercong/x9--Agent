from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False, suffix='.db').name}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import classify_reply  # noqa: E402


def test_classify_reply_categories():
    assert classify_reply("Sounds interesting, happy to collaborate.") == "interested"
    assert classify_reply("Can you send more campaign details?") == "need_more_info"
    assert classify_reply("What is your rate and commission?") == "negotiation"
    assert classify_reply("Thanks but not interested.") == "not_interested"
    assert classify_reply("Delivery failed, invalid address.") == "bounce_or_invalid"
    assert classify_reply("Thanks.") == "unclear"


def test_simulate_reply_runs_agent_and_persists_run():
    init_db()
    client = TestClient(app)
    creator = client.post(
        "/api/followup-agent/creators",
        json={
            "id": "creator_test_1",
            "handle": "creator_test",
            "display_name": "Creator Test",
            "email": "creator@example.com",
            "recommendation_reason": "Audience overlaps with mom and baby care.",
        },
    )
    assert creator.status_code == 200, creator.text

    reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={
            "creator_id": "creator_test_1",
            "from_email": "creator@example.com",
            "subject": "Re: Collaboration",
            "body": "Sounds interesting. Can you send more campaign details?",
            "run_agent": True,
        },
    )
    assert reply.status_code == 200, reply.text
    payload = reply.json()
    assert payload["run"]["reply_category"] == "need_more_info"
    assert payload["run"]["llm_status"] == "not_configured"
    assert payload["run"]["output"]["next_action"] == "send_campaign_details"

    listed = client.get("/api/followup-agent/runs?creator_id=creator_test_1")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
