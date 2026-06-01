from __future__ import annotations

import os
from typing import Any, Iterable, TypedDict

import httpx


# Retargeted to the X9 desktop backend (Phase 2-E). The scrapers push recruitment
# leads into x9db via /api/local/{company-leads,talents}/ingest. Those endpoints
# require a logged-in session, so we authenticate once with a foreign-trade
# department account (X9_INGEST_USERNAME / X9_INGEST_PASSWORD) and reuse the
# session cookie — the lead's department_code is resolved from that account.
DEFAULT_BACKEND_BASE = "http://127.0.0.1:8000"


def backend_base() -> str:
    return os.getenv(
        "X9_INGEST_BASE",
        os.getenv("COMPANYLEADS_BACKEND_URL", DEFAULT_BACKEND_BASE),
    ).strip().rstrip("/")


def api_headers() -> dict[str, str]:
    # Optional static header for environments that gate ingest with a token.
    token = os.getenv("X9_INGEST_TOKEN", "").strip()
    return {"X-X9-Ingest-Token": token} if token else {}


def company_ingest_url() -> str:
    return f"{backend_base()}/api/local/company-leads/ingest"


def talent_ingest_url() -> str:
    return f"{backend_base()}/api/local/talents/ingest"


# ---- session auth (login once, reuse cookie) ----
_AUTH: dict[str, Any] = {"cookies": None, "tried": False}


def _login_cookies() -> httpx.Cookies | None:
    """Login with the configured foreign-trade account; cache the cookie jar."""
    if _AUTH["cookies"] is not None or _AUTH["tried"]:
        return _AUTH["cookies"]
    _AUTH["tried"] = True
    user = os.getenv("X9_INGEST_USERNAME", "").strip()
    pwd = os.getenv("X9_INGEST_PASSWORD", "").strip()
    if not user or not pwd:
        print("[AUTH-WARN] X9_INGEST_USERNAME / X9_INGEST_PASSWORD not set; ingest will likely return 401")
        return None
    try:
        with _client() as client:
            resp = client.post(f"{backend_base()}/api/local/auth/login", json={"username": user, "password": pwd})
            if resp.status_code == 200:
                _AUTH["cookies"] = client.cookies
                return client.cookies
            print(f"[AUTH-WARN] login failed {resp.status_code}: {resp.text[:120]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[AUTH-WARN] {exc}")
    return None


def _client() -> httpx.Client:
    """httpx client pre-loaded with the X9 session cookie."""
    return httpx.Client(timeout=10, cookies=_login_cookies())


BACKEND_BASE = DEFAULT_BACKEND_BASE
BACKEND_URL = f"{DEFAULT_BACKEND_BASE}/api/local/company-leads/ingest"
TALENT_URL = f"{DEFAULT_BACKEND_BASE}/api/local/talents/ingest"


def _is_talent_entry(entry: dict[str, Any]) -> bool:
    """简历类条目 → 入人才库。
    判定：① source_mode=='recruiter'，或② 直接带 talent 字段（platform_resume_id / desired_title / name_masked）
    """
    if (entry.get("source_mode") or "").lower() == "recruiter":
        return True
    return bool(
        entry.get("platform_resume_id")
        or entry.get("desired_title")
        or entry.get("name_masked")
    )


def _to_talent_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """把爬虫产出的字段映射到 /api/talents/ingest 期望的字段名。"""
    raw = entry.get("raw_data") or {}
    name = entry.get("name_masked") or entry.get("name") or ""
    # 早期 qzrc 把 "[求职者:XX]" 塞到 company_name；如果没有 name，从这里反解一次
    if not name and entry.get("company_name", "").startswith("[求职者:"):
        name = entry["company_name"][len("[求职者:"):-1]
    return {
        "platform": entry.get("platform", "qzrc"),
        "platform_resume_id": entry.get("platform_resume_id") or entry.get("platform_company_id"),
        "name_masked": name or None,
        "desired_title": entry.get("desired_title") or entry.get("jd_title"),
        "city": entry.get("city"),
        "experience": entry.get("experience"),
        "education": entry.get("education"),
        "major": entry.get("major"),
        "salary_expectation": entry.get("salary_expectation") or entry.get("salary_range"),
        "source_url": entry.get("source_url"),
        "resume_download_url": raw.get("resume_download_url") or entry.get("resume_download_url"),
        "raw_summary": entry.get("raw_summary") or entry.get("jd_description"),
        "search_keyword": entry.get("search_keyword") or entry.get("search_keywords") or raw.get("keyword"),
        "search_keywords": entry.get("search_keywords") or entry.get("search_keyword") or raw.get("keyword"),
        "raw_data": raw or entry,
    }
TALENT_BACKEND_URL = f"{DEFAULT_BACKEND_BASE}/api/local/talents/ingest"


class CompanyLeadEntry(TypedDict, total=False):
    platform: str
    platform_company_id: str
    company_name: str
    jd_title: str
    city: str
    salary_range: str
    industry: str
    size_range: str
    company_address: str
    company_description: str
    contact_name: str
    contact_email: str
    contact_phone: str
    hr_wechat: str
    source_url: str
    source_mode: str
    jd_description: str
    raw_data: dict[str, Any]


class TalentLeadEntry(TypedDict, total=False):
    platform: str
    platform_resume_id: str
    name_masked: str
    desired_title: str
    city: str
    experience: str
    education: str
    major: str
    salary_expectation: str
    source_url: str
    resume_download_url: str
    raw_summary: str
    search_keyword: str
    search_keywords: str


def split_keywords(raw: str, default_keywords: Iterable[str]) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()] if raw else list(default_keywords)


def identity_key(entry: dict[str, Any]) -> str:
    stable_id = (
        entry.get("platform_company_id")
        or entry.get("source_url")
        or entry.get("company_name")
        or ""
    )
    return f"{entry.get('platform', '')}:{stable_id}:{entry.get('jd_title', '')}"


COMPANY_CONTRACT_FIELDS = [
    "platform",
    "platform_company_id",
    "company_name",
    "jd_title",
    "city",
    "salary_range",
    "industry",
    "size_range",
    "company_address",
    "company_description",
    "contact_name",
    "contact_email",
    "contact_phone",
    "hr_wechat",
    "source_url",
    "source_mode",
    "jd_description",
    "search_keyword",
    "search_keywords",
    "raw_data",
]


def normalize_company_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a stable /api/companies/ingest-shaped payload.

    Scrapers can discover fields in different phases. This keeps the public
    contract stable without forcing every platform to fill every field.
    """
    normalized: dict[str, Any] = {field: entry.get(field, "") for field in COMPANY_CONTRACT_FIELDS}
    normalized["platform"] = normalized.get("platform") or "51job"
    normalized["source_mode"] = normalized.get("source_mode") or "job_seeker"
    raw_data = normalized.get("raw_data")
    normalized["raw_data"] = raw_data if isinstance(raw_data, dict) else {"raw": raw_data} if raw_data else {}
    if not normalized.get("search_keyword") and isinstance(normalized["raw_data"], dict):
        normalized["search_keyword"] = normalized["raw_data"].get("keyword", "")
    if not normalized.get("search_keywords"):
        normalized["search_keywords"] = normalized.get("search_keyword", "")
    return normalized


def dedupe_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for raw_entry in entries:
        entry = normalize_company_entry(raw_entry)
        key = identity_key(entry)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def push_all(entries: list[dict[str, Any]], *, dry_run: bool, backend_url: str | None = None) -> None:
    deduped = dedupe_entries(entries)

    if dry_run:
        contact_count = sum(
            1 for e in deduped
            if e.get("contact_phone") or e.get("contact_email") or e.get("hr_wechat")
        )
        print(f"[DRY-RUN] 带联系方式 {contact_count} / {len(deduped)} 条")
        print(f"[DRY-RUN] 共 {len(deduped)} 条，前 5 条:")
        for e in deduped[:5]:
            contact = e.get("contact_phone") or e.get("contact_email") or e.get("hr_wechat") or "无联系方式"
            print(f"  {e.get('company_name')} / {e.get('jd_title')} / {e.get('city')} / {contact}")
        contacted = [
            e for e in deduped
            if e.get("contact_phone") or e.get("contact_email") or e.get("hr_wechat")
        ]
        if contacted:
            print("[DRY-RUN] 前 5 条带联系方式:")
            for e in contacted[:5]:
                contact = e.get("contact_phone") or e.get("contact_email") or e.get("hr_wechat")
                print(f"  {e.get('company_name')} / {e.get('jd_title')} / {e.get('city')} / {contact}")
        return

    ok = fail = 0
    ok_talent = 0
    llm_scored = llm_failed = 0
    company_url = backend_url or company_ingest_url()
    talent_url = talent_ingest_url()
    headers = api_headers()
    with _client() as client:
        for entry in deduped:
            is_talent = _is_talent_entry(entry)
            url = talent_url if is_talent else company_url
            payload = _to_talent_payload(entry) if is_talent else entry
            try:
                r = client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    ok += 1
                    if is_talent:
                        ok_talent += 1
                    try:
                        body = r.json()
                        if body.get("llm_score_status") == "scored":
                            llm_scored += 1
                        elif body.get("llm_score_status") == "failed":
                            llm_failed += 1
                    except Exception:
                        pass
                else:
                    fail += 1
                    if fail <= 3:
                        print(f"[WARN] {url} {r.status_code}: {r.text[:160]}")
            except Exception as exc:
                fail += 1
                if fail <= 3:
                    print(f"[WARN] {exc}")
    print(f"[DONE] 推送 {ok} 成功 (其中人才 {ok_talent}) / {fail} 失败，共 {len(deduped)} 条；LLM scored={llm_scored} failed={llm_failed}")


def push_one(entry: dict[str, Any], *, dry_run: bool, backend_url: str | None = None) -> bool:
    """Upsert one entry immediately while the scraper keeps its run summary."""
    if dry_run:
        return True

    normalized = normalize_company_entry(entry)
    is_talent = _is_talent_entry(normalized)
    url = talent_ingest_url() if is_talent else (backend_url or company_ingest_url())
    payload = _to_talent_payload(normalized) if is_talent else normalized
    try:
        with _client() as client:
            response = client.post(url, json=payload, headers=api_headers())
        if response.status_code == 200:
            llm_status = ""
            try:
                body = response.json()
                if body.get("llm_score_status"):
                    llm_status = f" / llm={body.get('llm_score_status')}"
            except Exception:
                pass
            print(
                f"[UPSERT] ok {payload.get('platform')} / "
                f"{payload.get('company_name') or payload.get('name_masked') or '-'} / "
                f"{payload.get('jd_title') or payload.get('desired_title') or '-'}{llm_status}"
            )
            return True
        print(f"[UPSERT-WARN] {url} {response.status_code}: {response.text[:160]}")
        return False
    except Exception as exc:
        print(f"[UPSERT-WARN] {exc}")
        return False


def talent_identity_key(entry: dict[str, Any]) -> str:
    stable_id = (
        entry.get("platform_resume_id")
        or entry.get("source_url")
        or f"{entry.get('name_masked', '')}:{entry.get('desired_title', '')}"
    )
    return f"{entry.get('platform', '')}:{stable_id}"


def dedupe_talents(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        key = talent_identity_key(entry)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def push_talents(entries: list[dict[str, Any]], *, dry_run: bool, backend_url: str | None = None) -> None:
    deduped = dedupe_talents(entries)

    if dry_run:
        print(f"[DRY-RUN] 人才线索 {len(deduped)} 条，前 8 条:")
        for e in deduped[:8]:
            print(
                f"  {e.get('name_masked') or '-'} / {e.get('desired_title')} / "
                f"{e.get('experience') or '-'} / {e.get('city') or '-'}"
            )
        return

    ok = fail = 0
    llm_scored = llm_failed = 0
    url = backend_url or talent_ingest_url()
    headers = api_headers()
    with _client() as client:
        for entry in deduped:
            try:
                r = client.post(url, json=entry, headers=headers)
                if r.status_code == 200:
                    ok += 1
                    try:
                        body = r.json()
                        if body.get("llm_score_status") == "scored":
                            llm_scored += 1
                        elif body.get("llm_score_status") == "failed":
                            llm_failed += 1
                    except Exception:
                        pass
                else:
                    fail += 1
                    if fail <= 3:
                        print(f"[WARN] talent {r.status_code}: {r.text[:120]}")
            except Exception as exc:
                fail += 1
                if fail <= 3:
                    print(f"[WARN] talent {exc}")
    print(f"[DONE] 人才推送 {ok} 成功 / {fail} 失败，共 {len(deduped)} 条；LLM scored={llm_scored} failed={llm_failed}")
