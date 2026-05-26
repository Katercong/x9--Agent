"""Tests for the outreach (建联) email feature.

Gmail send is mocked at the service boundary so these tests run with no
network access and no google-* dependencies installed.
"""
from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from x9_creator_desktop_system.backend.database.connection import SessionLocal
from x9_creator_desktop_system.backend.main import app
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.gmail_account import GmailAccount
from x9_creator_desktop_system.backend.models.outreach_email import OutreachEmail
from x9_creator_desktop_system.backend.models.outreach_template import OutreachTemplate
from x9_creator_desktop_system.backend.routers.creators import _fetch_outreach_signals
from x9_creator_desktop_system.backend.services import auth_service, gmail_service
from x9_creator_desktop_system.backend.services.ai_writer import _compact_context
from x9_creator_desktop_system.backend.services.outreach_service import (
    build_context,
    generate_with_ai,
    generate_x9_care_keyword_script,
    pick_template,
    render_template,
)
from desktop.backend.services import gmail_service as desktop_gmail_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_creator():
    """Insert a deterministic creator row, yield it, clean up."""
    with SessionLocal() as session:
        creator = Creator(
            id="creator_outreach_test_1",
            platform="tiktok",
            handle="testcreator",
            display_name="Test Creator",
            profile_url="https://www.tiktok.com/@testcreator",
            bio="Mom of two sharing daily essentials and self-care tips.",
            followers_count=12500,
            email="creator@example.com",
            has_email=1,
            recommended_product_type="feminine_care",
            recommended_collab_type="sample_collab",
            store_assigned="x9_us_store",
            owner_bd="Alice",
            current_status="待建联",
            collected_at=datetime(2026, 5, 1, 12, 0, 0),
            source_video_title="My morning routine for sensitive skin",
            matched_keywords_json='["self-care","period","sensitive skin"]',
        )
        session.merge(creator)
        session.commit()
        creator_id = creator.id
    yield creator_id
    with SessionLocal() as session:
        session.query(OutreachEmail).filter_by(creator_id=creator_id).delete()
        c = session.get(Creator, creator_id)
        if c is not None:
            session.delete(c)
        session.commit()


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_build_context_uses_creator_fields(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        ctx = build_context(creator, sender_name="Alice")
    assert ctx["handle"] == "testcreator"
    assert ctx["display_name"] == "Test Creator"
    assert ctx["product_label"] == "女性护理"
    assert ctx["collab_label"] == "寄样合作"
    # bio_hint should mention something from the bio
    assert ctx["bio_hint"]
    # video_hint quotes the source video title
    assert "morning routine" in ctx["video_hint"]
    # matched_keywords joined with chinese punctuation
    assert "self-care" in ctx["matched_keywords"]


def test_default_templates_are_seeded():
    with SessionLocal() as session:
        count = session.query(OutreachTemplate).count()
    assert count >= 1, "default templates should be seeded on init_db"


def test_pick_template_prefers_collab_match(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        tpl = pick_template(session, creator, language="zh")
    assert tpl is not None
    # creator.recommended_collab_type == "sample_collab", so template should match
    assert tpl.collab_type in (None, "sample_collab")


def test_render_template_substitutes_placeholders(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        tpl = pick_template(session, creator, language="zh")
        assert tpl is not None
        rendered = render_template(tpl, creator, sender_name="Alice")
    assert "${" not in rendered.subject
    assert "${" not in rendered.body
    assert "testcreator" in rendered.body or "Test Creator" in rendered.subject


def test_x9_care_keyword_script_uses_user_keywords(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        rendered = generate_x9_care_keyword_script(
            creator,
            "baby diapers, pet review, authentic mom, TikTok Shop",
        )
    assert rendered.ai_status == "keyword_reference"
    assert "Mercy" in rendered.body
    assert "baby diapers" in rendered.body
    assert "pet care pads" in rendered.body
    assert "TikTok Shop" in rendered.body
    assert "Just reply \"YES\"" in rendered.body


def test_generate_with_ai_uses_creator_context(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        creator.queue_type = "sample_collab_test_queue"
        creator.recommendation_reason = "Bio and video both mention self-care."
        tpl = pick_template(session, creator, language="zh")
        assert tpl is not None

        def fake_polish(subject, body, context, **kwargs):
            assert context["recommendation_reason"]
            assert context["product_label"]
            assert context["collab_label"]
            assert context["queue_label"]
            assert context["bio_excerpt"]
            assert kwargs["tone"] == "friendly"
            assert kwargs["language"] == "en"
            return [{"subject": "AI subject", "body": "AI body"}]

        with patch("x9_creator_desktop_system.backend.config.settings", SimpleNamespace(openai_api_key="test")):
            with patch(
                "x9_creator_desktop_system.backend.services.ai_writer.polish_email",
                side_effect=fake_polish,
            ):
                rendered = generate_with_ai(tpl, creator, use_ai=True)

    assert rendered.subject == "AI subject"
    assert rendered.body == "AI body"
    assert rendered.ai_used is True
    assert rendered.ai_status == "generated"


def test_generate_with_ai_reports_not_configured(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        tpl = pick_template(session, creator, language="zh")
        assert tpl is not None

        with patch("x9_creator_desktop_system.backend.config.settings", SimpleNamespace(openai_api_key="")):
            rendered = generate_with_ai(tpl, creator, use_ai=True)

    assert rendered.ai_used is False
    assert rendered.ai_status == "not_configured"
    assert rendered.subject


def test_html_gmail_message_inlines_product_asset_image(tmp_path):
    image_path = tmp_path / "product.png"
    image_path.write_bytes(b"x9-image-bytes")
    html = (
        '<p>Hello creator</p>'
        '<img src="/api/local/outreach/product-assets/sku_inline_test/image" alt="Product">'
    )

    with patch.object(desktop_gmail_service.product_asset_service, "get_asset", return_value={"id": "sku_inline_test"}):
        with patch.object(desktop_gmail_service.product_asset_service, "image_path", return_value=image_path):
            with patch.object(desktop_gmail_service.product_asset_service, "guess_mime_type", return_value="image/png"):
                raw = desktop_gmail_service._build_mime_message(
                    to_email="creator@example.com",
                    subject="Inline image",
                    body=html,
                    body_format="html",
                    from_email="bd@example.com",
                    department_code="cross_border",
                )

    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw.encode("utf-8")))
    assert message.get_content_type() == "multipart/related"
    html_parts = [part for part in message.walk() if part.get_content_type() == "text/html"]
    assert html_parts
    assert 'src="cid:x9-product-sku_inline_test@x9.local"' in html_parts[0].get_content()
    image_parts = [part for part in message.walk() if part.get_content_type() == "image/png"]
    assert image_parts
    assert image_parts[0]["Content-ID"] == "<x9-product-sku_inline_test@x9.local>"


def test_ai_context_prioritizes_recommendation_table_fields(sample_creator):
    with SessionLocal() as session:
        creator = session.get(Creator, sample_creator)
        creator.queue_type = "sample_collab_test_queue"
        creator.recommendation_reason = "Bio and video both mention self-care."
        ctx = build_context(creator)

    compact = _compact_context(ctx)
    primary = compact["primary_reference_fields"]
    assert primary["reason"] == "Bio and video both mention self-care."
    assert primary["product"]
    assert primary["collaboration"]
    assert primary["queue"]
    assert "Mom of two" in primary["creator_bio"]


# ---------------------------------------------------------------------------
# Router-level tests
# ---------------------------------------------------------------------------


def test_list_templates_returns_seeded_rows(client):
    r = client.get("/api/local/outreach/templates")
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True
    assert payload["total"] >= 1
    assert all("subject_template" in t for t in payload["items"])


def test_preview_endpoint_renders(client, sample_creator):
    r = client.post(f"/api/local/outreach/preview/{sample_creator}", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["to_email"] == "creator@example.com"
    assert body["has_email"] is True
    assert body["subject"]
    assert body["body"]
    assert "${" not in body["subject"]
    assert "${" not in body["body"]
    assert body["ai_status"] == "template"


def test_create_draft_then_patch_then_send(client, sample_creator):
    # 1. create draft
    create = client.post(
        "/api/local/outreach/draft",
        json={"creator_id": sample_creator},
    )
    assert create.status_code == 200, create.text
    draft = create.json()
    assert draft["status"] == "draft"
    assert draft["to_email"] == "creator@example.com"
    draft_id = draft["id"]

    # 2. patch the subject
    patch_r = client.patch(
        f"/api/local/outreach/draft/{draft_id}",
        json={"subject": "Edited subject"},
    )
    assert patch_r.status_code == 200
    assert patch_r.json()["subject"] == "Edited subject"

    # 3. send (mock Gmail)
    fake_send = {"message_id": "abc123", "thread_id": "thread_x", "from_email": "me@x9.com"}
    with patch.object(gmail_service, "send_email", return_value=fake_send) as mock_send:
        send_r = client.post(
            f"/api/local/outreach/send/{draft_id}",
            json={"confirm": True, "update_creator_status": True},
        )
    assert send_r.status_code == 200, send_r.text
    sent = send_r.json()
    assert sent["status"] == "sent"
    assert sent["gmail_message_id"] == "abc123"
    mock_send.assert_called_once()
    current_user = client.get("/api/local/auth/me").json()["user"]
    assert mock_send.call_args.kwargs["user_id"] == current_user["id"]
    assert mock_send.call_args.kwargs["include_shared"] is False
    # creator current_status should now be "已建联"
    creator_after = client.get(f"/api/local/creators/{sample_creator}").json()
    assert creator_after["current_status"] == "已建联"


def test_send_without_authorization_marks_failed(client, sample_creator):
    create = client.post("/api/local/outreach/draft", json={"creator_id": sample_creator})
    draft_id = create.json()["id"]

    def boom(**_kw):
        raise gmail_service.GmailNotAuthorizedError("not authorized")

    with patch.object(gmail_service, "send_email", side_effect=boom):
        r = client.post(
            f"/api/local/outreach/send/{draft_id}",
            json={"confirm": True},
        )
    assert r.status_code == 401
    # draft should be marked failed for retry
    drafts = client.get(f"/api/local/outreach/drafts?creator_id={sample_creator}").json()
    matching = [d for d in drafts["items"] if d["id"] == draft_id]
    assert matching and matching[0]["status"] == "failed"


def test_history_endpoint(client, sample_creator):
    client.post("/api/local/outreach/draft", json={"creator_id": sample_creator})
    r = client.get(f"/api/local/outreach/history/{sample_creator}")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_outreach_signals_normalize_numeric_creator_ids():
    creator_id = "987654321"
    email_id = "outreach_numeric_creator_signal"
    with SessionLocal() as session:
        session.query(OutreachEmail).filter_by(id=email_id).delete()
        session.add(
            OutreachEmail(
                id=email_id,
                department_code="cross_border",
                creator_id=creator_id,
                to_email="creator@example.com",
                from_email="bd@example.com",
                subject="hello",
                body="body",
                status="sent",
                sent_at=datetime(2026, 5, 11, 9, 0, 0),
            )
        )
        session.commit()

    try:
        signals = _fetch_outreach_signals([int(creator_id)])
        assert signals[creator_id]["outreach_count"] == 1
        assert signals[creator_id]["last_outreach_sender_email"] == "bd@example.com"
    finally:
        with SessionLocal() as session:
            session.query(OutreachEmail).filter_by(id=email_id).delete()
            session.commit()


def test_gmail_status_does_not_crash_without_creds(client):
    """The status endpoint should be safe to hit before any setup."""
    r = client.get("/api/local/outreach/gmail/status")
    assert r.status_code == 200
    body = r.json()
    assert "configured" in body
    assert "authorized" in body


def test_admin_gmail_status_excludes_legacy_unbound_account(client):
    account_id = "gmail_legacy_unbound"
    with SessionLocal() as session:
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.add(
            GmailAccount(
                id=account_id,
                email="legacy-unbound@example.com",
                display_name="Legacy Unbound",
                token_json="{}",
                is_default=0,
                is_active=1,
            )
        )
        session.commit()

    try:
        r = client.get("/api/local/outreach/gmail/status")
        assert r.status_code == 200
        accounts = r.json()["accounts"]
        assert not any(account["id"] == account_id for account in accounts)
    finally:
        with SessionLocal() as session:
            session.query(GmailAccount).filter_by(id=account_id).delete()
            session.commit()


def test_matching_legacy_gmail_account_is_claimed_by_current_user():
    account_id = "gmail_legacy_claimed_by_user"
    with SessionLocal() as session:
        user = auth_service.upsert_user(
            session,
            username="gmail_claim_user",
            email="claim-user@example.com",
            password="TempPass123!",
            role="department_user",
            department_code="cross_border",
            approval_status=auth_service.ACTIVE_STATUS,
        )
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.query(GmailAccount).filter_by(email="claim-user@example.com").delete()
        session.add(
            GmailAccount(
                id=account_id,
                email="claim-user@example.com",
                display_name="Claim User",
                token_json="{}",
                is_default=1,
                is_active=1,
            )
        )
        user_id = user.id
        token, _ = auth_service.create_session_for_user(session, user, entry_scope="workspace")

    c = TestClient(app)
    c.cookies.set(auth_service.SESSION_COOKIE, token)
    try:
        r = c.get("/api/local/outreach/gmail/status")
        assert r.status_code == 200
        body = r.json()
        assert body["authorized"] is True
        assert any(account["id"] == account_id for account in body["accounts"])
        with SessionLocal() as session:
            row = session.get(GmailAccount, account_id)
            assert row is not None
            assert row.user_id == user_id
    finally:
        with SessionLocal() as session:
            session.query(GmailAccount).filter_by(id=account_id).delete()
            session.commit()


def test_gmail_upsert_rejects_account_bound_to_other_user():
    account_id = "gmail_owned_by_other_user"
    email = "owned-gmail@example.com"
    with SessionLocal() as session:
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.query(GmailAccount).filter_by(email=email).delete()
        session.add(
            GmailAccount(
                id=account_id,
                user_id="owner_a",
                department_code="cross_border",
                email=email,
                display_name="Owned Gmail",
                token_json="{}",
                is_default=1,
                is_active=1,
            )
        )
        session.commit()

        with pytest.raises(gmail_service.GmailNotAuthorizedError):
            gmail_service._upsert_authorized_account(
                session,
                user_email=email,
                raw_token_json='{"refresh_token":"new"}',
                label=None,
                user_id="owner_b",
                department_code="cross_border",
            )
    with SessionLocal() as session:
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.commit()


def test_gmail_upsert_claims_unowned_account_for_authorizing_user():
    account_id = "gmail_unowned_claimed_on_authorize"
    email = "claim-on-authorize@example.com"
    raw_token = '{"refresh_token":"new"}'
    with SessionLocal() as session:
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.query(GmailAccount).filter_by(email=email).delete()
        session.add(
            GmailAccount(
                id=account_id,
                email=email,
                display_name="Claim On Authorize",
                token_json="{}",
                is_default=0,
                is_active=1,
            )
        )
        session.commit()

        row = gmail_service._upsert_authorized_account(
            session,
            user_email=email,
            raw_token_json=raw_token,
            label="workspace",
            user_id="owner_b",
            department_code="cross_border",
        )
        assert row.id == account_id
        assert row.user_id == "owner_b"
        assert row.department_code == "cross_border"
        assert row.is_default == 1
        assert gmail_service._token_json_from_storage(row.token_json) == raw_token
        session.commit()
    with SessionLocal() as session:
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.commit()
def test_department_user_does_not_see_shared_gmail_account():
    account_id = "gmail_shared_hidden_from_department"
    with SessionLocal() as session:
        user = auth_service.upsert_user(
            session,
            username="gmail_dept_user",
            password="TempPass123!",
            role="department_user",
            department_code="cross_border",
            approval_status=auth_service.ACTIVE_STATUS,
        )
        session.query(GmailAccount).filter_by(id=account_id).delete()
        session.add(
            GmailAccount(
                id=account_id,
                email="shared-visible@example.com",
                display_name="Shared Visible",
                token_json="{}",
                is_default=1,
                is_active=1,
            )
        )
        token, _ = auth_service.create_session_for_user(session, user, entry_scope="workspace")

    c = TestClient(app)
    c.cookies.set(auth_service.SESSION_COOKIE, token)
    try:
        r = c.get("/api/local/outreach/gmail/status")
        assert r.status_code == 200
        body = r.json()
        assert body["authorized"] is False
        assert not any(account["id"] == account_id for account in body["accounts"])
    finally:
        with SessionLocal() as session:
            session.query(GmailAccount).filter_by(id=account_id).delete()
            session.commit()
