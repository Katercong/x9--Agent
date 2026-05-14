"""LLM provider management + unified completion proxy.

Endpoints (all auth-required for writes):
    GET    /api/v1/llm/providers                  list providers (api_key always masked)
    GET    /api/v1/llm/providers/{code}           one provider (masked)
    GET    /api/v1/llm/active                     currently active provider
    PUT    /api/v1/llm/providers/{code}           update provider (auth)
    POST   /api/v1/llm/providers/{code}/activate  set active (auth)
    POST   /api/v1/llm/providers/{code}/test      ping the provider with a 5-token completion (auth)
    DELETE /api/v1/llm/providers/{code}/key       wipe the api_key (auth)
    POST   /api/v1/llm/providers                  add a new provider (auth)
    POST   /api/v1/llm/complete                   unified completion call (auth)

Frontend "Settings" tab uses these.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_authenticated, require_admin

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

router = APIRouter()

EDITABLE = {"display_name", "type", "api_key", "base_url", "default_model",
            "extra_headers", "enabled", "sort_order"}


def get_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "*" * 6 + key[-4:]


def row_to_dict(row: sqlite3.Row, *, include_key: bool = False) -> dict:
    d = dict(row)
    if not include_key:
        d["api_key"] = mask(d.get("api_key"))
        d["api_key_set"] = bool(row["api_key"])
    if d.get("extra_headers"):
        try:
            d["extra_headers"] = json.loads(d["extra_headers"])
        except json.JSONDecodeError:
            pass
    return d


def get_provider(code: str, *, include_key: bool = False) -> dict:
    con = get_con()
    try:
        row = con.execute("SELECT * FROM llm_provider WHERE code=?", (code,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, f"unknown provider '{code}'")
    return row_to_dict(row, include_key=include_key)


def get_provider_for_feature(feature_code: str, *, include_key: bool = True) -> tuple[dict, dict]:
    """For a given feature, return (provider, feature) — provider has the key
    needed to call the LLM. Falls back to globally active provider if the
    feature has no explicit binding.

    Raises HTTPException(400) if neither feature-binding nor active provider
    has a usable api_key.
    """
    con = get_con()
    try:
        feat = con.execute(
            "SELECT * FROM llm_feature WHERE code=? AND enabled=1", (feature_code,)
        ).fetchone()
        if not feat:
            raise HTTPException(404, f"unknown feature '{feature_code}'")
        feat_d = dict(feat)
        # Resolve provider: feature.provider_code -> else global is_active
        prov_code = feat_d.get("provider_code")
        prov_row = None
        if prov_code:
            prov_row = con.execute(
                "SELECT * FROM llm_provider WHERE code=?", (prov_code,)
            ).fetchone()
        if not prov_row:
            prov_row = con.execute(
                "SELECT * FROM llm_provider WHERE is_active=1"
            ).fetchone()
        if not prov_row:
            raise HTTPException(
                400,
                f"feature '{feature_code}' has no provider binding and no global active provider"
            )
        prov = row_to_dict(prov_row, include_key=include_key)
        if not prov.get("api_key"):
            raise HTTPException(
                400,
                f"feature '{feature_code}' resolved to provider '{prov['code']}' but it has no API key set"
            )
        # Apply feature's model override if any
        if feat_d.get("model"):
            prov["default_model"] = feat_d["model"]
        return prov, feat_d
    finally:
        con.close()


# ============================================================
# Endpoints
# ============================================================
@router.get("/api/v1/llm/providers")
def list_providers() -> dict:
    con = get_con()
    rows = con.execute("SELECT * FROM llm_provider ORDER BY sort_order, code").fetchall()
    con.close()
    items = [row_to_dict(r) for r in rows]
    active = next((r["code"] for r in items if r.get("is_active")), None)
    return {"items": items, "active": active}


@router.get("/api/v1/llm/active")
def get_active() -> dict:
    con = get_con()
    row = con.execute("SELECT * FROM llm_provider WHERE is_active=1").fetchone()
    con.close()
    if not row:
        return {"active": None, "message": "no provider activated; PUT a key + POST /activate first"}
    return {"active": row_to_dict(row)}


@router.get("/api/v1/llm/providers/{code}")
def get_provider_endpoint(code: str) -> dict:
    return get_provider(code)


@router.put("/api/v1/llm/providers/{code}", dependencies=[Depends(require_admin)])
async def update_provider(code: str, payload: dict) -> dict:
    fields = {k: v for k, v in payload.items() if k in EDITABLE}
    if not fields:
        raise HTTPException(400, f"no editable fields (allowed: {sorted(EDITABLE)})")
    if "extra_headers" in fields and not isinstance(fields["extra_headers"], str):
        fields["extra_headers"] = json.dumps(fields["extra_headers"] or {}, ensure_ascii=False)
    fields["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    con = get_con()
    try:
        if not con.execute("SELECT 1 FROM llm_provider WHERE code=?", (code,)).fetchone():
            raise HTTPException(404, f"unknown provider '{code}'")
        sets = ",".join([f"{k}=?" for k in fields])
        con.execute(f"UPDATE llm_provider SET {sets} WHERE code=?",
                    list(fields.values()) + [code])
        con.commit()
    finally:
        con.close()
    return get_provider(code)


@router.post("/api/v1/llm/providers", dependencies=[Depends(require_admin)])
async def create_provider(payload: dict) -> dict:
    code = payload.get("code")
    if not code:
        raise HTTPException(400, "missing 'code'")
    if not all(c.isalnum() or c in "_-" for c in code):
        raise HTTPException(400, "code may only contain a-z 0-9 _ -")
    typ = payload.get("type", "openai_compat")
    if typ not in {"anthropic", "openai_compat"}:
        raise HTTPException(400, "type must be 'anthropic' or 'openai_compat'")
    fields = {k: v for k, v in payload.items() if k in EDITABLE | {"code"}}
    fields.setdefault("display_name", code)
    if "extra_headers" in fields and not isinstance(fields["extra_headers"], str):
        fields["extra_headers"] = json.dumps(fields["extra_headers"] or {}, ensure_ascii=False)
    cols = list(fields.keys())
    placeholders = ",".join(["?"] * len(cols))
    con = get_con()
    try:
        if con.execute("SELECT 1 FROM llm_provider WHERE code=?", (code,)).fetchone():
            raise HTTPException(409, f"provider '{code}' already exists")
        con.execute(f"INSERT INTO llm_provider({','.join(cols)}) VALUES({placeholders})",
                    [fields[c] for c in cols])
        con.commit()
    finally:
        con.close()
    return get_provider(code)


@router.post("/api/v1/llm/providers/{code}/activate", dependencies=[Depends(require_admin)])
async def activate_provider(code: str) -> dict:
    con = get_con()
    try:
        row = con.execute("SELECT api_key FROM llm_provider WHERE code=?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, f"unknown provider '{code}'")
        if not row["api_key"]:
            raise HTTPException(400, f"cannot activate '{code}' without an api_key — PUT key first")
        con.execute("UPDATE llm_provider SET is_active=0")
        con.execute("UPDATE llm_provider SET is_active=1, updated_at=? WHERE code=?",
                    (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), code))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "active": code}


@router.delete("/api/v1/llm/providers/{code}/key", dependencies=[Depends(require_admin)])
async def clear_key(code: str) -> dict:
    con = get_con()
    try:
        if not con.execute("SELECT 1 FROM llm_provider WHERE code=?", (code,)).fetchone():
            raise HTTPException(404, f"unknown provider '{code}'")
        con.execute("UPDATE llm_provider SET api_key=NULL, is_active=0 WHERE code=?", (code,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "cleared": code}


@router.post("/api/v1/llm/providers/{code}/test", dependencies=[Depends(require_admin)])
async def test_provider(code: str) -> dict:
    """Ping the provider with a tiny prompt; record result."""
    p = get_provider(code, include_key=True)
    try:
        result = _call(p, messages=[{"role": "user", "content": "Say OK."}],
                       system="Reply with one word.", max_tokens=8, temperature=0)
        status = "ok"
        msg = (result.get("content") or "")[:200]
    except Exception as e:
        status = "error"
        msg = str(e)[:300]
    con = get_con()
    try:
        con.execute("UPDATE llm_provider SET last_tested_at=?, last_test_status=?, "
                    "last_test_message=? WHERE code=?",
                    (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), status, msg, code))
        con.commit()
    finally:
        con.close()
    return {"code": code, "status": status, "message": msg}


# ============================================================
# Per-feature LLM binding
# ============================================================
@router.get("/api/v1/llm/features")
def list_features() -> dict:
    """List all AI features + their current provider/model binding (or fallback)."""
    con = get_con()
    rows = con.execute(
        "SELECT f.*, p.display_name AS provider_display_name, "
        "p.default_model AS provider_default_model "
        "FROM llm_feature f LEFT JOIN llm_provider p ON p.code=f.provider_code "
        "ORDER BY f.sort_order, f.code"
    ).fetchall()
    # also fetch the global fallback so frontend can show 'fallback: <provider>'
    fallback = con.execute(
        "SELECT code, display_name, default_model FROM llm_provider WHERE is_active=1"
    ).fetchone()
    con.close()
    items = []
    for r in rows:
        d = dict(r)
        d["resolved_provider"] = d.get("provider_code") or (fallback["code"] if fallback else None)
        d["resolved_model"] = d.get("model") or d.get("provider_default_model") or (
            fallback["default_model"] if fallback else None
        )
        d["bound"] = bool(d.get("provider_code"))
        items.append(d)
    return {
        "items": items,
        "global_fallback": dict(fallback) if fallback else None,
    }


@router.get("/api/v1/llm/features/{code}")
def get_feature(code: str) -> dict:
    con = get_con()
    row = con.execute(
        "SELECT f.*, p.display_name AS provider_display_name "
        "FROM llm_feature f LEFT JOIN llm_provider p ON p.code=f.provider_code "
        "WHERE f.code=?", (code,)
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, f"unknown feature '{code}'")
    return dict(row)


@router.put("/api/v1/llm/features/{code}", dependencies=[Depends(require_admin)])
async def update_feature(code: str, payload: dict) -> dict:
    """Bind a feature to a specific provider+model, or unbind (set null) to use global active."""
    EDITABLE_F = {"display_name", "description", "provider_code", "model",
                  "temperature", "max_tokens", "enabled"}
    fields = {k: v for k, v in payload.items() if k in EDITABLE_F}
    if not fields:
        raise HTTPException(400, f"no editable fields (allowed: {sorted(EDITABLE_F)})")
    # validate provider_code if non-null
    if fields.get("provider_code"):
        con = get_con()
        try:
            ok = con.execute(
                "SELECT 1 FROM llm_provider WHERE code=?", (fields["provider_code"],)
            ).fetchone()
        finally:
            con.close()
        if not ok:
            raise HTTPException(404, f"provider '{fields['provider_code']}' not found")
    fields["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    con = get_con()
    try:
        if not con.execute("SELECT 1 FROM llm_feature WHERE code=?", (code,)).fetchone():
            raise HTTPException(404, f"unknown feature '{code}'")
        sets = ",".join([f"{k}=?" for k in fields])
        con.execute(f"UPDATE llm_feature SET {sets} WHERE code=?",
                    list(fields.values()) + [code])
        con.commit()
    finally:
        con.close()
    return get_feature(code)


@router.delete("/api/v1/llm/features/{code}/binding", dependencies=[Depends(require_admin)])
async def unbind_feature(code: str) -> dict:
    """Clear feature's provider binding so it falls back to global active."""
    con = get_con()
    try:
        if not con.execute("SELECT 1 FROM llm_feature WHERE code=?", (code,)).fetchone():
            raise HTTPException(404, f"unknown feature '{code}'")
        con.execute(
            "UPDATE llm_feature SET provider_code=NULL, model=NULL, updated_at=? WHERE code=?",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), code)
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "code": code, "message": "now uses global active provider"}


@router.post("/api/v1/llm/complete", dependencies=[Depends(require_authenticated)])
async def complete(payload: dict) -> dict:
    """Unified completion call. Falls back to active provider if `provider` not given."""
    provider_code = payload.get("provider")
    if not provider_code:
        con = get_con()
        try:
            row = con.execute("SELECT code FROM llm_provider WHERE is_active=1").fetchone()
        finally:
            con.close()
        if not row:
            raise HTTPException(400, "no active provider; activate one first")
        provider_code = row["code"]
    p = get_provider(provider_code, include_key=True)
    if not p["api_key"]:
        raise HTTPException(400, f"provider '{provider_code}' has no api_key set")
    messages = payload.get("messages")
    if not messages:
        raise HTTPException(400, "missing 'messages'")
    try:
        return _call(
            p,
            messages=messages,
            system=payload.get("system"),
            max_tokens=payload.get("max_tokens", 1500),
            temperature=payload.get("temperature", 0.7),
            model=payload.get("model"),
        )
    except RuntimeError as e:
        raise HTTPException(502, f"upstream provider error: {e}")
    except requests.RequestException as e:
        raise HTTPException(502, f"network error calling provider: {e}")


# ============================================================
# Provider call adapters
# ============================================================
def _call(provider: dict, *, messages: list[dict], system: "str | list | None" = None,
          model: str | None = None, max_tokens: int = 1500, temperature: float = 0.7) -> dict:
    typ = provider["type"]
    model = model or provider.get("default_model")
    if typ == "anthropic":
        return _call_anthropic(provider, messages, system, model, max_tokens, temperature)
    elif typ == "openai_compat":
        # openai_compat expects a plain string; flatten list to text if needed
        sys_str = system if isinstance(system, str) or system is None else (
            " ".join(b.get("text", "") for b in system if isinstance(b, dict))
        )
        return _call_openai_compat(provider, messages, sys_str, model, max_tokens, temperature)
    raise ValueError(f"unknown provider type {typ!r}")


def _call_anthropic(p: dict, messages: list[dict], system: "str | list | None",
                    model: str, max_tokens: int, temperature: float) -> dict:
    base = (p.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
    url = f"{base}/messages"
    headers = {
        "x-api-key": p["api_key"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    # Prompt caching: activated when system is passed as a content-block list with cache_control
    if isinstance(system, list):
        headers["anthropic-beta"] = "prompt-caching-2024-07-31"
    headers.update(_extra_headers(p))
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        body["system"] = system
    r = requests.post(url, json=body, headers=headers, timeout=60)
    if not r.ok:
        raise RuntimeError(f"anthropic {r.status_code}: {r.text[:300]}")
    data = r.json()
    text = "".join([blk.get("text", "") for blk in data.get("content", []) if blk.get("type") == "text"])
    usage = data.get("usage", {})
    return {
        "provider": p["code"], "model": model, "content": text,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
    }


def _call_openai_compat(p: dict, messages: list[dict], system: str | None,
                        model: str, max_tokens: int, temperature: float) -> dict:
    base = (p.get("base_url") or "").rstrip("/")
    if not base:
        raise RuntimeError(f"provider '{p['code']}' missing base_url")
    url = f"{base}/chat/completions"
    msgs = list(messages)
    if system:
        msgs = [{"role": "system", "content": system}] + msgs
    headers = {
        "Authorization": f"Bearer {p['api_key']}",
        "Content-Type": "application/json",
    }
    headers.update(_extra_headers(p))
    body = {
        "model": model,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = requests.post(url, json=body, headers=headers, timeout=60)
    if not r.ok:
        raise RuntimeError(f"{p['code']} {r.status_code}: {r.text[:300]}")
    data = r.json()
    text = ""
    if data.get("choices"):
        text = (data["choices"][0].get("message") or {}).get("content", "")
    usage = data.get("usage") or {}
    return {
        "provider": p["code"], "model": model, "content": text,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
    }


def _extra_headers(p: dict) -> dict[str, str]:
    raw = p.get("extra_headers")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    try:
        return {str(k): str(v) for k, v in json.loads(raw).items()}
    except Exception:
        return {}
