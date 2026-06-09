from __future__ import annotations

import csv
import io
import json

from sqlalchemy import inspect

from x9_creator_desktop_system.backend.database import engine as main_engine
from x9_creator_desktop_system.backend.models.youtube_lead import YoutubeLead, YoutubeLeadSource, YoutubeRawRow
from x9_creator_desktop_system.backend.services.departments import DEFAULT_DEPARTMENT
from x9_creator_desktop_system.backend.services.youtube_import_service import import_youtube_export
from x9_creator_desktop_system.backend.youtube_database import YoutubeSessionLocal


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _rows_payload(rows: list[dict], *, keyword: str = "shop evaluation") -> dict:
    return {
        "result": {
            "keyword": keyword,
            "source_search_url": f"https://www.youtube.com/results?search_query={keyword.replace(' ', '+')}",
            "rows": rows,
        }
    }


def _lead_by_key(channel_key: str) -> YoutubeLead | None:
    with YoutubeSessionLocal() as db:
        return db.query(YoutubeLead).filter(YoutubeLead.channel_key == channel_key).one_or_none()


def test_youtube_import_dry_run_filters_rows_without_writing() -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "dry001",
                "video_url": "https://www.youtube.com/watch?v=dry001",
                "creator_channel_url": "https://www.youtube.com/@YTImportDryEmail",
                "email": "SALES@Example.COM",
            },
            {
                "source_type": "comment_author_channel",
                "video_id": "dry001",
                "video_url": "https://www.youtube.com/watch?v=dry001",
                "comment_author_name": "No Contact",
                "comment_author_channel_url": "https://www.youtube.com/@YTImportDryDrop",
            },
            {
                "source_type": "comment_author_channel",
                "video_id": "dry001",
                "video_url": "https://www.youtube.com/watch?v=dry001",
                "comment_author_name": "Manual",
                "comment_author_channel_url": "https://www.youtube.com/@YTImportDryReview/about",
                "needs_manual_review": True,
                "review_reason": "hidden_email_button_present",
                "manual_review_url": "https://www.youtube.com/@YTImportDryReview/about",
            },
        ]
    )

    with YoutubeSessionLocal() as db:
        result = import_youtube_export(db, _json_bytes(payload), filename="dry.json", dry_run=True)

    assert result["dry_run"] is True
    assert result["total_rows"] == 3
    assert result["kept"] == 2
    assert result["dropped_no_contact"] == 1
    assert result["manual_review"] == 1
    assert _lead_by_key("handle:@ytimportdryemail") is None
    assert _lead_by_key("handle:@ytimportdryreview") is None


def test_youtube_import_api_writes_json_state(client) -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "api001",
                "video_title": "API Import Video",
                "video_url": "https://www.youtube.com/watch?v=api001",
                "creator_channel_url": "https://www.youtube.com/@YTImportApiEmail",
                "email": "Creator@Example.com",
                "emails_json": '["creator@example.com", "alt@example.com"]',
                "evidence_url": "https://www.youtube.com/watch?v=api001",
                "collected_at": "2026-06-06T12:00:00Z",
            },
            {
                "source_type": "comment_author_channel",
                "video_id": "api001",
                "video_url": "https://www.youtube.com/watch?v=api001",
                "comment_author_name": "Empty Commenter",
                "comment_author_channel_url": "https://www.youtube.com/@YTImportApiDrop",
            },
            {
                "source_type": "comment_author_channel",
                "video_id": "api001",
                "video_url": "https://www.youtube.com/watch?v=api001",
                "comment_author_name": "Review Commenter",
                "comment_author_channel_url": "https://www.youtube.com/@YTImportApiReview",
                "hidden_email_button_present": "true",
                "manual_review_url": "https://www.youtube.com/@YTImportApiReview/about",
            },
        ],
        keyword="api keyword",
    )

    response = client.post("/api/local/youtube/import?filename=api.json", content=_json_bytes(payload))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 3
    assert body["kept"] == 2
    assert body["dropped_no_contact"] == 1
    assert body["inserted"] == 2
    assert body["sources_added"] == 2
    assert body["manual_review"] == 1

    with YoutubeSessionLocal() as db:
        lead = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportapiemail").one()
        review = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportapireview").one()
        raw_rows = db.query(YoutubeRawRow).filter(YoutubeRawRow.run_id == body["run_id"]).all()

    assert lead.email == "creator@example.com"
    assert json.loads(lead.emails_json) == ["creator@example.com", "alt@example.com"]
    assert review.needs_manual_review == 1
    assert "hidden_email_button_present" in json.loads(review.review_reasons_json)
    assert len(raw_rows) == 3


def test_youtube_import_duplicate_file_deduplicates_lead_and_source(client) -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "dup001",
                "video_url": "https://www.youtube.com/watch?v=dup001",
                "creator_channel_url": "https://www.youtube.com/@YTImportDup",
                "email": "dup@example.com",
                "evidence_url": "https://www.youtube.com/watch?v=dup001",
            }
        ],
        keyword="duplicate keyword",
    )

    first = client.post("/api/local/youtube/import?filename=dup.json", content=_json_bytes(payload)).json()
    second = client.post("/api/local/youtube/import?filename=dup.json", content=_json_bytes(payload)).json()

    assert first["inserted"] == 1
    assert first["sources_added"] == 1
    assert second["inserted"] == 0
    assert second["updated"] == 1
    assert second["sources_added"] == 0

    with YoutubeSessionLocal() as db:
        lead = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportdup").one()
        sources = db.query(YoutubeLeadSource).filter(YoutubeLeadSource.lead_id == lead.id).all()
    assert len(sources) == 1


def test_youtube_import_duplicate_email_values_do_not_duplicate_lead_or_source(client) -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "dupmail001",
                "video_url": "https://www.youtube.com/watch?v=dupmail001",
                "creator_channel_url": "https://www.youtube.com/@YTImportDupMail",
                "email": "Repeat@Example.com",
                "emails_json": '["repeat@example.com", "REPEAT@example.com", "alt@example.com"]',
                "evidence_url": "https://www.youtube.com/watch?v=dupmail001",
            }
        ],
        keyword="duplicate email keyword",
    )

    first = client.post("/api/local/youtube/import?filename=dupmail.json", content=_json_bytes(payload)).json()
    second = client.post("/api/local/youtube/import?filename=dupmail.json", content=_json_bytes(payload)).json()

    assert first["inserted"] == 1
    assert first["sources_added"] == 1
    assert second["inserted"] == 0
    assert second["updated"] == 1
    assert second["sources_added"] == 0

    with YoutubeSessionLocal() as db:
        lead = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportdupmail").one()
        sources = db.query(YoutubeLeadSource).filter(YoutubeLeadSource.lead_id == lead.id).all()

    assert json.loads(lead.emails_json) == ["repeat@example.com", "alt@example.com"]
    assert len(sources) == 1


def test_youtube_import_csv_merges_same_channel_with_multiple_sources(client) -> None:
    rows = [
        {
            "source_type": "creator_channel",
            "keyword": "csv keyword",
            "video_id": "csv001",
            "video_url": "https://www.youtube.com/watch?v=csv001",
            "creator_channel_url": "https://www.youtube.com/@YTImportCsvSame",
            "email": "csv@example.com",
            "evidence_url": "https://www.youtube.com/watch?v=csv001",
        },
        {
            "source_type": "comment_author_channel",
            "keyword": "csv keyword",
            "video_id": "csv002",
            "video_url": "https://www.youtube.com/watch?v=csv002",
            "comment_author_name": "Same Channel",
            "comment_author_channel_url": "https://www.youtube.com/@YTImportCsvSame/about",
            "email": "csv@example.com",
            "evidence_url": "https://www.youtube.com/@YTImportCsvSame/about",
        },
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=sorted({key for row in rows for key in row}))
    writer.writeheader()
    writer.writerows(rows)

    response = client.post("/api/local/youtube/import?filename=same.csv", content=buffer.getvalue().encode("utf-8"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kept"] == 2
    assert body["inserted"] == 1
    assert body["updated"] == 1
    assert body["sources_added"] == 2

    with YoutubeSessionLocal() as db:
        lead = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportcsvsame").one()
        sources = db.query(YoutubeLeadSource).filter(YoutubeLeadSource.lead_id == lead.id).all()
    assert lead.email == "csv@example.com"
    assert len(sources) == 2


def test_youtube_import_uses_independent_youtube_database(client) -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "sep001",
                "video_url": "https://www.youtube.com/watch?v=sep001",
                "creator_channel_url": "https://www.youtube.com/@YTImportSeparateDb",
                "email": "separate@example.com",
            }
        ],
        keyword="separate db",
    )

    response = client.post("/api/local/youtube/import?filename=separate.json", content=_json_bytes(payload))

    assert response.status_code == 200, response.text
    assert inspect(main_engine).has_table("youtube_leads") is False
    assert _lead_by_key("handle:@ytimportseparatedb") is not None


def test_youtube_import_needs_manual_review_without_explicit_reason_is_dropped() -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "generic001",
                "video_url": "https://www.youtube.com/watch?v=generic001",
                "creator_channel_url": "https://www.youtube.com/@YTImportGenericReview",
                "needs_manual_review": True,
                "manual_review_url": "https://www.youtube.com/@YTImportGenericReview/about",
            }
        ],
        keyword="generic review",
    )

    with YoutubeSessionLocal() as db:
        result = import_youtube_export(db, _json_bytes(payload), filename="generic.json", dry_run=True)

    assert result["kept"] == 0
    assert result["dropped_no_contact"] == 1
    assert result["manual_review"] == 0


def test_youtube_import_email_update_clears_manual_review(client) -> None:
    review_payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "verify001",
                "video_url": "https://www.youtube.com/watch?v=verify001",
                "creator_channel_url": "https://www.youtube.com/@YTImportVerifyClear",
                "hidden_email_button_present": True,
                "manual_review_url": "https://www.youtube.com/@YTImportVerifyClear/about",
                "review_reason": "hidden_email_button_present",
            }
        ],
        keyword="verify clear",
    )
    email_payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "verify001",
                "video_url": "https://www.youtube.com/watch?v=verify001",
                "creator_channel_url": "https://www.youtube.com/@YTImportVerifyClear",
                "email": "verified@example.com",
                "email_source": "manual_verified_about",
                "evidence_url": "https://www.youtube.com/@YTImportVerifyClear/about",
            }
        ],
        keyword="verify clear",
    )

    first = client.post("/api/local/youtube/import?filename=verify-review.json", content=_json_bytes(review_payload))
    second = client.post("/api/local/youtube/import?filename=verify-email.json", content=_json_bytes(email_payload))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["manual_review"] == 1
    assert second.json()["updated"] == 1

    with YoutubeSessionLocal() as db:
        lead = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportverifyclear").one()
        sources = db.query(YoutubeLeadSource).filter(YoutubeLeadSource.lead_id == lead.id).all()

    assert lead.email == "verified@example.com"
    assert lead.has_email == 1
    assert lead.needs_manual_review == 0
    assert json.loads(lead.review_reasons_json) == []
    assert lead.manual_review_url is None
    assert any(source.review_reason == "hidden_email_button_present" for source in sources)

    review_response = client.get("/api/local/youtube/manual-review")
    leads_response = client.get("/api/local/youtube/leads?keyword=verify%20clear")

    assert review_response.status_code == 200
    assert leads_response.status_code == 200
    assert all(item["channel_handle"] != "@YTImportVerifyClear" for item in review_response.json()["items"])
    matching = [item for item in leads_response.json()["items"] if item["channel_handle"] == "@YTImportVerifyClear"]
    assert matching
    assert matching[0]["has_email"] is True
    assert matching[0]["needs_manual_review"] is False


def test_youtube_import_later_review_row_does_not_reopen_email_lead(client) -> None:
    email_payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "reverse001",
                "video_url": "https://www.youtube.com/watch?v=reverse001",
                "creator_channel_url": "https://www.youtube.com/@YTImportReverseClear",
                "email": "reverse@example.com",
                "evidence_url": "https://www.youtube.com/@YTImportReverseClear/about",
            }
        ],
        keyword="reverse clear",
    )
    review_payload = _rows_payload(
        [
            {
                "source_type": "comment_author_channel",
                "video_id": "reverse002",
                "video_url": "https://www.youtube.com/watch?v=reverse002",
                "comment_author_name": "Reverse Clear",
                "comment_author_channel_url": "https://www.youtube.com/@YTImportReverseClear",
                "hidden_email_button_present": True,
                "manual_review_url": "https://www.youtube.com/@YTImportReverseClear/about",
            }
        ],
        keyword="reverse clear",
    )

    first = client.post("/api/local/youtube/import?filename=reverse-email.json", content=_json_bytes(email_payload))
    second = client.post("/api/local/youtube/import?filename=reverse-review.json", content=_json_bytes(review_payload))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    with YoutubeSessionLocal() as db:
        lead = db.query(YoutubeLead).filter(YoutubeLead.channel_key == "handle:@ytimportreverseclear").one()
        sources = db.query(YoutubeLeadSource).filter(YoutubeLeadSource.lead_id == lead.id).all()

    assert lead.email == "reverse@example.com"
    assert lead.has_email == 1
    assert lead.needs_manual_review == 0
    assert json.loads(lead.review_reasons_json) == []
    assert lead.manual_review_url is None
    assert any(source.review_reason == "hidden_email_button_present" for source in sources)

    review_response = client.get("/api/local/youtube/manual-review")
    review_items = review_response.json()["items"]
    assert all(item["channel_handle"] != "@YTImportReverseClear" for item in review_items)


def test_youtube_manual_review_endpoint_hides_legacy_email_review_leads(client) -> None:
    with YoutubeSessionLocal() as db:
        db.add(
            YoutubeLead(
                department_code=DEFAULT_DEPARTMENT,
                platform="youtube",
                channel_key="handle:@ytimportlegacydirty",
                channel_handle="@YTImportLegacyDirty",
                channel_url="https://www.youtube.com/@YTImportLegacyDirty",
                email="legacy-dirty@example.com",
                emails_json='["legacy-dirty@example.com"]',
                has_email=1,
                needs_manual_review=1,
                review_reasons_json='["hidden_email_button_present"]',
                manual_review_url="https://www.youtube.com/@YTImportLegacyDirty/about",
            )
        )
        db.commit()

    manual = client.get("/api/local/youtube/manual-review")
    leads = client.get("/api/local/youtube/leads?needs_manual_review=true")

    assert manual.status_code == 200
    assert leads.status_code == 200
    assert all(item["channel_handle"] != "@YTImportLegacyDirty" for item in manual.json()["items"])
    assert all(item["channel_handle"] != "@YTImportLegacyDirty" for item in leads.json()["items"])


def test_youtube_query_endpoints(client) -> None:
    payload = _rows_payload(
        [
            {
                "source_type": "creator_channel",
                "video_id": "query001",
                "video_url": "https://www.youtube.com/watch?v=query001",
                "creator_channel_url": "https://www.youtube.com/@YTImportQueryEmail",
                "email": "query@example.com",
            },
            {
                "source_type": "comment_author_channel",
                "video_id": "query001",
                "video_url": "https://www.youtube.com/watch?v=query001",
                "comment_author_name": "Review Query",
                "comment_author_channel_url": "https://www.youtube.com/@YTImportQueryReview",
                "review_reason": "captcha_required",
                "manual_review_url": "https://www.youtube.com/@YTImportQueryReview/about",
            },
        ],
        keyword="query keyword",
    )
    response = client.post("/api/local/youtube/import?filename=query.json", content=_json_bytes(payload))
    assert response.status_code == 200, response.text

    runs = client.get("/api/local/youtube/runs")
    leads = client.get("/api/local/youtube/leads?keyword=query%20keyword")
    review = client.get("/api/local/youtube/manual-review")
    stats = client.get("/api/local/youtube/stats")
    actors = client.get("/api/local/youtube/actors")

    assert runs.status_code == 200
    assert leads.status_code == 200
    assert review.status_code == 200
    assert stats.status_code == 200
    assert actors.status_code == 200
    assert runs.json()["total"] >= 1
    assert leads.json()["total"] >= 2
    assert review.json()["total"] >= 1
    assert stats.json()["local_mode"] is True
    assert stats.json()["raw_rows"] >= 2
    assert stats.json()["leads"] >= 2
    assert stats.json()["manual_review"] >= 1
    assert actors.json()["items"][0]["id"] == "youtube_local_collector"
    assert actors.json()["items"][0]["collection"]["total"] >= 2

    lead_id = leads.json()["items"][0]["id"]
    sources = client.get(f"/api/local/youtube/sources?lead_id={lead_id}")
    assert sources.status_code == 200
    assert sources.json()["total"] >= 1
