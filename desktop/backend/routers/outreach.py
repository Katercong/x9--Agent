"""Outreach (建联) API: template management, draft preview, Gmail send.

Endpoints
---------
``GET    /api/local/outreach/templates``               list templates
``POST   /api/local/outreach/templates``               create a template
``PATCH  /api/local/outreach/templates/{tpl_id}``      update a template
``DELETE /api/local/outreach/templates/{tpl_id}``      delete a template

``POST   /api/local/outreach/preview/{creator_id}``    render a template
                                                       against a creator without
                                                       persisting

``POST   /api/local/outreach/draft``                   create a draft email row
``GET    /api/local/outreach/drafts``                  list drafts/sent emails
``GET    /api/local/outreach/history/{creator_id}``    history for one creator
``PATCH  /api/local/outreach/draft/{draft_id}``        edit subject/body/recipient
``DELETE /api/local/outreach/draft/{draft_id}``        cancel a draft
``POST   /api/local/outreach/send/{draft_id}``         send via Gmail

``GET    /api/local/outreach/gmail/status``            authorized? configured?
``GET    /api/local/outreach/gmail/auth-url``          start OAuth (browser)
``GET    /api/local/outreach/gmail/callback``          OAuth redirect target
``POST   /api/local/outreach/gmail/disconnect``        delete stored token
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.creator import Creator
from ..models.creator_outreach_lock import CreatorOutreachLock
from ..models.outreach_email import OutreachEmail
from ..models.outreach_template import OutreachTemplate
from ..services import gmail_service
from ..services import product_asset_service
from ..services import remote_creators
from ..services.departments import current_department_code, department_where, effective_row_department, row_in_department
from ..services.remote_creators import RemoteRepoError
from ..services.post_processing import create_outreach_event
from ..services.outreach_lock_service import (
    acquire_creator_lock,
    actor_id,
    heartbeat_lock,
    is_admin_user,
    release_creator_lock_if_owned,
    release_lock,
    require_creator_lock,
    serialize_lock,
    utcnow,
)
from ..services.outreach_service import (
    context_to_json,
    generate_with_ai,
    generate_x9_care_keyword_script,
    pick_template,
    render_template,
)
from ..services.tk_script_service import (
    build_tk_context,
    build_tk_email_subject,
    delete_prompt as _delete_tk_prompt,
    generate_strategy_ai,
    generate_strategy_hybrid,
    generate_strategy_template,
    list_prompts as _list_tk_prompts,
    save_prompt as _save_tk_prompt,
)
from ..utils.id_utils import new_id


router = APIRouter(prefix="/api/local/outreach", tags=["outreach"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TemplateIn(BaseModel):
    name: str
    description: str | None = None
    language: str = "zh"
    collab_type: str | None = None
    product_type: str | None = None
    subject_template: str
    body_template: str
    sender_name: str | None = None
    sender_signature: str | None = None
    is_default: bool = False
    is_active: bool = True
    tone: str | None = Field(default=None, pattern="^(formal|casual|friendly)$")
    max_length: int | None = Field(default=None, ge=80, le=2000)


class TemplatePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    language: str | None = None
    collab_type: str | None = None
    product_type: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    sender_name: str | None = None
    sender_signature: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    tone: str | None = Field(default=None, pattern="^(formal|casual|friendly)$")
    max_length: int | None = Field(default=None, ge=80, le=2000)


class PreviewIn(BaseModel):
    template_id: str | None = None
    language: str | None = None
    sender_name: str | None = None
    sender_signature: str | None = None
    use_ai: bool = False
    # AI generation knobs — all optional, default to template / built-in.
    tone: str | None = Field(default=None, pattern="^(formal|casual|friendly)$")
    max_length: int | None = Field(default=None, ge=80, le=2000)
    # Number of variants to return when use_ai=True. 1 returns just subject/body.
    # 2-3 also fills the ``variants`` array for the N-choose-1 picker.
    n: int = Field(default=1, ge=1, le=3)
    script_keywords: str | None = Field(default=None, max_length=500)


class DraftIn(BaseModel):
    creator_id: str
    template_id: str | None = None
    to_email: EmailStr | None = None
    subject: str | None = None
    body: str | None = None
    body_format: str = Field(default="plain", pattern="^(plain|html)$")
    sender_name: str | None = None
    sender_signature: str | None = None
    ai_versions: list[dict[str, str]] | None = None
    ai_tone: str | None = Field(default=None, pattern="^(formal|casual|friendly)$")
    ai_language: str | None = None


class DraftPatch(BaseModel):
    to_email: EmailStr | None = None
    subject: str | None = None
    body: str | None = None
    body_format: str | None = Field(default=None, pattern="^(plain|html)$")
    ai_versions: list[dict[str, str]] | None = None
    ai_tone: str | None = Field(default=None, pattern="^(formal|casual|friendly)$")
    ai_language: str | None = None


class SendIn(BaseModel):
    confirm: bool = True
    update_creator_status: bool = True
    from_account_id: str | None = None


class RollbackIn(BaseModel):
    """Restore the subject/body of one historical email into the current draft."""

    target_email_id: str


class LockAcquireIn(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=60, le=3600)
    force: bool = False


class LockHeartbeatIn(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=60, le=3600)


class LockReleaseIn(BaseModel):
    force: bool = False
    reason: str | None = Field(default=None, max_length=200)


class TkScriptIn(BaseModel):
    commission: int = Field(default=20, ge=5, le=20)
    strategy: str = Field(default="template", pattern="^(template|ai|hybrid)$")
    custom_prompt: str | None = Field(default=None, max_length=4000)
    prompt_id: str | None = None
    product_asset_id: str | None = None


class TkPromptIn(BaseModel):
    name: str = Field(max_length=100)
    prompt: str = Field(max_length=4000)
    strategy: str = Field(default="ai", pattern="^(ai|hybrid)$")


class ProductAssetIn(BaseModel):
    name: str = Field(max_length=120)
    sku_code: str | None = Field(default=None, max_length=80)
    product_key: str = Field(default="all", max_length=80)
    selling_points: list[str] = Field(default_factory=list)
    target_creator_types: list[str] = Field(default_factory=list)
    image_data_url: str | None = Field(default=None, max_length=12_000_000)
    is_active: bool = True


class ProductAssetPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    sku_code: str | None = Field(default=None, max_length=80)
    product_key: str | None = Field(default=None, max_length=80)
    selling_points: list[str] | None = None
    target_creator_types: list[str] | None = None
    image_data_url: str | None = Field(default=None, max_length=12_000_000)
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _template_to_dict(tpl: OutreachTemplate) -> dict[str, Any]:
    return {
        "id": tpl.id,
        "department_code": tpl.department_code,
        "name": tpl.name,
        "description": tpl.description,
        "language": tpl.language,
        "collab_type": tpl.collab_type,
        "product_type": tpl.product_type,
        "subject_template": tpl.subject_template,
        "body_template": tpl.body_template,
        "sender_name": tpl.sender_name,
        "sender_signature": tpl.sender_signature,
        "is_default": bool(tpl.is_default),
        "is_active": bool(tpl.is_active),
        "tone": getattr(tpl, "tone", None),
        "max_length": getattr(tpl, "max_length", None),
        "created_at": _iso(tpl.created_at),
        "updated_at": _iso(tpl.updated_at),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _email_to_dict(email: OutreachEmail) -> dict[str, Any]:
    return {
        "id": email.id,
        "department_code": email.department_code,
        "creator_id": email.creator_id,
        "template_id": email.template_id,
        "to_email": email.to_email,
        "from_email": email.from_email,
        "subject": email.subject,
        "body": email.body,
        "body_format": email.body_format,
        "status": email.status,
        "review_required": bool(email.review_required),
        "auto_send": bool(email.auto_send),
        "gmail_message_id": email.gmail_message_id,
        "gmail_thread_id": email.gmail_thread_id,
        "error_message": email.error_message,
        "parent_email_id": getattr(email, "parent_email_id", None),
        "ai_tone": getattr(email, "ai_tone", None),
        "ai_language": getattr(email, "ai_language", None),
        "ai_versions_json": getattr(email, "ai_versions_json", None),
        "sent_at": _iso(email.sent_at),
        "created_at": _iso(email.created_at),
        "updated_at": _iso(email.updated_at),
    }


def _body_preview(value: str | None, body_format: str | None = None, limit: int = 180) -> str:
    text = value or ""
    if (body_format or "").lower() == "html":
        text = re.sub(r"<(br|/p|/div|/li)\b[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _creator_summary(creator: Creator | dict[str, Any] | None) -> dict[str, Any]:
    if creator is None:
        return {}
    if isinstance(creator, dict):
        return {
            "creator_handle": creator.get("handle"),
            "creator_display_name": creator.get("display_name"),
            "creator_profile_url": creator.get("profile_url"),
            "creator_platform": creator.get("platform"),
        }
    return {
        "creator_handle": creator.handle,
        "creator_display_name": creator.display_name,
        "creator_profile_url": creator.profile_url,
        "creator_platform": creator.platform,
    }


def _creator_summary_map(db: Session, creator_ids: list[str], department_code: str | None) -> dict[str, dict[str, Any]]:
    ids = [str(cid) for cid in dict.fromkeys(creator_ids) if str(cid or "").strip()]
    if not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    local_rows = list(db.scalars(select(Creator).where(Creator.id.in_(ids))).all())
    for creator in local_rows:
        if row_in_department(creator, department_code):
            out[str(creator.id)] = _creator_summary(creator)
    for creator_id in ids:
        if creator_id in out or not creator_id.isdigit():
            continue
        try:
            row = remote_creators.get_by_id(creator_id)
        except RemoteRepoError:
            row = None
        if row is not None and row_in_department(row, department_code):
            out[creator_id] = _creator_summary(row)
    return out


def _archive_item_to_dict(email: OutreachEmail, creator_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": email.id,
        "department_code": email.department_code,
        "creator_id": email.creator_id,
        **(creator_summary or {}),
        "to_email": email.to_email,
        "from_email": email.from_email,
        "subject": email.subject,
        "body_preview": _body_preview(email.body, email.body_format),
        "body_format": email.body_format,
        "status": email.status,
        "sent_at": _iso(email.sent_at),
        "created_at": _iso(email.created_at),
        "created_by": getattr(email, "created_by", None),
        "gmail_thread_id": email.gmail_thread_id,
        "parent_email_id": getattr(email, "parent_email_id", None),
    }


def _archive_detail_to_dict(email: OutreachEmail, creator_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    item = _archive_item_to_dict(email, creator_summary)
    item.update(
        {
            "body": email.body,
            "gmail_message_id": email.gmail_message_id,
            "error_message": email.error_message,
            "updated_at": _iso(email.updated_at),
        }
    )
    return item


def _parse_archive_datetime(value: str | None, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be ISO datetime or YYYY-MM-DD") from exc


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.get("/templates")
def list_templates(
    request: Request,
    language: str | None = Query(default=None),
    collab_type: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    q = select(OutreachTemplate)
    department_code = current_department_code(request)
    if department_code is not None:
        q = q.where((OutreachTemplate.department_code == department_code) | (OutreachTemplate.department_code.is_(None)))
    if not include_inactive:
        q = q.where(OutreachTemplate.is_active == 1)
    if language:
        q = q.where(OutreachTemplate.language == language)
    if collab_type:
        q = q.where(OutreachTemplate.collab_type == collab_type)
    q = q.order_by(OutreachTemplate.is_default.desc(), OutreachTemplate.name.asc())
    rows = list(db.scalars(q).all())
    return {"ok": True, "total": len(rows), "items": [_template_to_dict(r) for r in rows]}


@router.post("/templates")
def create_template(body: TemplateIn, request: Request, db: Session = Depends(get_db)) -> dict:
    tpl = OutreachTemplate(
        id=new_id("tpl"),
        department_code=current_department_code(request),
        name=body.name,
        description=body.description,
        language=body.language or "zh",
        collab_type=body.collab_type,
        product_type=body.product_type,
        subject_template=body.subject_template,
        body_template=body.body_template,
        sender_name=body.sender_name,
        sender_signature=body.sender_signature,
        is_default=1 if body.is_default else 0,
        is_active=1 if body.is_active else 0,
        tone=body.tone,
        max_length=body.max_length,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return _template_to_dict(tpl)


@router.patch("/templates/{tpl_id}")
def update_template(tpl_id: str, body: TemplatePatch, request: Request, db: Session = Depends(get_db)) -> dict:
    tpl = db.get(OutreachTemplate, tpl_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="template not found")
    if tpl.department_code is not None and not row_in_department(tpl, current_department_code(request)):
        raise HTTPException(status_code=404, detail="template not found")
    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if key in {"is_default", "is_active"} and value is not None:
            setattr(tpl, key, 1 if value else 0)
        else:
            setattr(tpl, key, value)
    db.commit()
    db.refresh(tpl)
    return _template_to_dict(tpl)


@router.delete("/templates/{tpl_id}")
def delete_template(tpl_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    tpl = db.get(OutreachTemplate, tpl_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="template not found")
    if tpl.department_code is not None and not row_in_department(tpl, current_department_code(request)):
        raise HTTPException(status_code=404, detail="template not found")
    db.delete(tpl)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Preview / draft / send
# ---------------------------------------------------------------------------


def _resolve_creator(db: Session, creator_id: str, department_code: str | None = None) -> Creator:
    creator = db.get(Creator, creator_id)
    if creator is not None:
        if not row_in_department(creator, department_code):
            raise HTTPException(status_code=404, detail="creator not found")
        return creator

    try:
        row = None
        if str(creator_id).isdigit():
            row = remote_creators.get_by_id(creator_id)
        elif "_" in creator_id:
            prefix, _, handle = creator_id.partition("_")
            platform_map = {"tt": "tiktok", "ig": "instagram", "yt": "youtube"}
            platform = platform_map.get(prefix)
            if platform and handle:
                row = remote_creators.get_by_handle(platform, handle)
    except RemoteRepoError as exc:
        raise HTTPException(status_code=502, detail=f"remote API unavailable: {exc}") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if not row_in_department(row, department_code):
        raise HTTPException(status_code=404, detail="creator not found")
    return _remote_row_to_creator(row)


def _remote_row_to_creator(row: dict[str, Any]) -> Creator:
    """Create a transient Creator-shaped object from a remote API row.

    Outreach rendering only needs attribute access; the remote creator itself
    stays in Zhang's database, while local SQLite stores only email drafts.
    """
    creator = Creator(
        id=str(row.get("id") or ""),
        platform=str(row.get("platform") or "tiktok"),
        handle=str(row.get("handle") or ""),
        department_code=str(row.get("department_code") or "cross_border"),
    )
    for key in (
        "display_name",
        "profile_url",
        "bio",
        "followers_count",
        "email",
        "recommended_product_type",
        "recommended_collab_type",
        "queue_type",
        "recommendation_reason",
        "risk_summary",
        "next_action",
        "store_assigned",
        "owner_bd",
        "current_status",
        "source_video_title",
        "source_video_description",
        "search_keyword",
        "matched_keywords_json",
    ):
        if key in row:
            setattr(creator, key, row.get(key))
    if row.get("matched_keywords") is not None and not row.get("matched_keywords_json"):
        creator.matched_keywords_json = row.get("matched_keywords")
    return creator


@router.post("/preview/{creator_id}")
def preview_email(creator_id: str, body: PreviewIn, request: Request, db: Session = Depends(get_db)) -> dict:
    creator = _resolve_creator(db, creator_id, current_department_code(request))
    script_keywords = (body.script_keywords or "").strip()
    if script_keywords:
        rendered = generate_x9_care_keyword_script(
            creator,
            script_keywords,
            sender_name=body.sender_name,
            sender_signature=body.sender_signature,
        )
        return {
            "ok": True,
            "template_id": None,
            "template_name": "X9 Care keyword reference",
            "to_email": creator.email or "",
            "has_email": bool(creator.email),
            "subject": rendered.subject,
            "body": rendered.body,
            "body_format": "plain",
            "context": rendered.context,
            "ai_used": rendered.ai_used,
            "ai_status": rendered.ai_status,
            "ai_message": rendered.ai_message,
            "tone": rendered.tone,
            "language": rendered.language,
            "variants": rendered.variants or [],
        }
    requested_language = "en" if body.use_ai else body.language
    template = pick_template(
        db, creator, template_id=body.template_id, language=requested_language
    )
    if body.use_ai and template is not None and template.language != "en":
        template = pick_template(db, creator, template_id=None, language="en") or template
    if template is None:
        raise HTTPException(
            status_code=400,
            detail="no active outreach templates configured. Create one in /api/local/outreach/templates first.",
        )
    rendered = generate_with_ai(
        template,
        creator,
        use_ai=body.use_ai,
        sender_name=body.sender_name,
        sender_signature=body.sender_signature,
        tone=body.tone,
        language=requested_language,
        max_length=body.max_length,
        n=body.n,
    )
    return {
        "ok": True,
        "template_id": template.id,
        "template_name": template.name,
        "to_email": creator.email or "",
        "has_email": bool(creator.email),
        "subject": rendered.subject,
        "body": rendered.body,
        "body_format": "plain",
        "context": rendered.context,
        "ai_used": rendered.ai_used,
        "ai_status": rendered.ai_status,
        "ai_message": rendered.ai_message,
        "tone": rendered.tone,
        "language": rendered.language,
        "variants": rendered.variants or [],
    }


# ---------------------------------------------------------------------------
# Short-lived creator outreach locks
# ---------------------------------------------------------------------------


@router.get("/locks/mine")
def list_my_outreach_locks(request: Request, db: Session = Depends(get_db)) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    owner = actor_id(current_user)
    if not owner:
        raise HTTPException(status_code=401, detail="login required")
    rows = list(
        db.scalars(
            select(CreatorOutreachLock)
            .where(CreatorOutreachLock.owner_user_id == owner)
            .where(CreatorOutreachLock.released_at.is_(None))
            .where(CreatorOutreachLock.expires_at > utcnow())
            .order_by(CreatorOutreachLock.expires_at.desc())
        ).all()
    )
    return {"ok": True, "total": len(rows), "items": [serialize_lock(row, current_user) for row in rows]}


@router.get("/locks/active")
def list_active_outreach_locks(request: Request, db: Session = Depends(get_db)) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    if not is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="admin only")
    q = (
        select(CreatorOutreachLock)
        .where(CreatorOutreachLock.released_at.is_(None))
        .where(CreatorOutreachLock.expires_at > utcnow())
        .order_by(CreatorOutreachLock.expires_at.desc())
    )
    where_department = department_where(CreatorOutreachLock, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    rows = list(db.scalars(q).all())
    return {"ok": True, "total": len(rows), "items": [serialize_lock(row, current_user) for row in rows]}


@router.post("/locks/{creator_id}")
def acquire_outreach_lock(
    creator_id: str,
    body: LockAcquireIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    department_code = current_department_code(request)
    creator = _resolve_creator(db, creator_id, department_code)
    current_user = getattr(request.state, "current_user", None) or {}
    lock = acquire_creator_lock(
        db,
        creator_id=str(creator.id),
        department_code=effective_row_department(creator),
        user=current_user,
        ttl_seconds=body.ttl_seconds,
        force=body.force,
    )
    return {"ok": True, "lock": serialize_lock(lock, current_user)}


@router.post("/locks/{lock_id}/heartbeat")
def heartbeat_outreach_lock(
    lock_id: str,
    body: LockHeartbeatIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    lock = heartbeat_lock(db, lock_id=lock_id, user=current_user, ttl_seconds=body.ttl_seconds)
    return {"ok": True, "lock": serialize_lock(lock, current_user)}


@router.post("/locks/{lock_id}/release")
def release_outreach_lock(
    lock_id: str,
    body: LockReleaseIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    lock = release_lock(db, lock_id=lock_id, user=current_user, force=body.force, reason=body.reason)
    return {"ok": True, "lock": serialize_lock(lock, current_user)}


# ---------------------------------------------------------------------------
# TK script prompt template management
# ---------------------------------------------------------------------------


@router.get("/tk-prompts")
def list_tk_prompts() -> dict:
    """List saved TK script prompt templates."""
    items = _list_tk_prompts()
    return {"items": items, "total": len(items)}


@router.post("/tk-prompts")
def create_tk_prompt(body: TkPromptIn) -> dict:
    """Save a custom TK script prompt template."""
    entry = _save_tk_prompt(name=body.name, prompt=body.prompt, strategy=body.strategy)
    return {"ok": True, "prompt": entry}


@router.delete("/tk-prompts/{prompt_id}")
def remove_tk_prompt(prompt_id: str) -> dict:
    """Delete a saved TK script prompt template."""
    ok = _delete_tk_prompt(prompt_id)
    if not ok:
        raise HTTPException(status_code=404, detail="prompt not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Product/SKU asset library
# ---------------------------------------------------------------------------


@router.get("/product-assets")
def list_product_assets(
    request: Request,
    creator_id: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """List local outreach product assets and optionally return a creator match."""
    department_code = current_department_code(request)
    items = product_asset_service.list_assets(
        department_code,
        include_inactive=include_inactive,
    )
    matched = None
    if creator_id:
        creator = _resolve_creator(db, creator_id, department_code)
        matched = product_asset_service.match_asset_for_creator(creator, items)
    return {"ok": True, "items": items, "total": len(items), "matched": matched}


@router.post("/product-assets")
def create_product_asset(body: ProductAssetIn, request: Request) -> dict:
    """Save a local product/SKU asset, including an optional base64 image."""
    try:
        asset = product_asset_service.save_asset(
            body.model_dump(),
            department_code=current_department_code(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "asset": asset}


@router.patch("/product-assets/{asset_id}")
def update_product_asset(asset_id: str, body: ProductAssetPatch, request: Request) -> dict:
    try:
        asset = product_asset_service.update_asset(
            asset_id,
            body.model_dump(exclude_unset=True),
            department_code=current_department_code(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="product asset not found")
    return {"ok": True, "asset": asset}


@router.delete("/product-assets/{asset_id}")
def delete_product_asset(asset_id: str, request: Request) -> dict:
    ok = product_asset_service.delete_asset(asset_id, department_code=current_department_code(request))
    if not ok:
        raise HTTPException(status_code=404, detail="product asset not found")
    return {"ok": True}


@router.get("/product-assets/{asset_id}/image")
def get_product_asset_image(asset_id: str, request: Request):
    asset = product_asset_service.get_asset(asset_id, department_code=current_department_code(request))
    if not asset:
        raise HTTPException(status_code=404, detail="product asset not found")
    path = product_asset_service.image_path(asset)
    if not path:
        raise HTTPException(status_code=404, detail="product image not found")
    return FileResponse(path, media_type=product_asset_service.guess_mime_type(path))


# ---------------------------------------------------------------------------
# TK DM script generation
# ---------------------------------------------------------------------------


@router.post("/tk-script/{creator_id}")
def generate_tk_dm_script(
    creator_id: str,
    body: TkScriptIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Generate a personalized TikTok DM outreach script.

    Three strategies:
    - template: ${var} substitution with creator context (bio, video, keywords)
    - ai:       LLM generates the entire script given creator context + system prompt
    - hybrid:   Fixed X9 brand frame + LLM writes personalized opener only
    """
    department_code = current_department_code(request)
    creator = _resolve_creator(db, creator_id, department_code)
    product_asset = None
    if body.product_asset_id:
        product_asset = product_asset_service.get_asset(body.product_asset_id, department_code=department_code)
        if product_asset is None:
            raise HTTPException(status_code=404, detail="product asset not found")
    else:
        product_asset = product_asset_service.match_asset_for_creator(
            creator,
            product_asset_service.list_assets(department_code),
        )
    ctx = build_tk_context(creator, commission=body.commission, product_asset=product_asset)

    custom_prompt = (body.custom_prompt or "").strip() or None
    if body.prompt_id and not custom_prompt:
        for prompt in _list_tk_prompts():
            if prompt.get("id") == body.prompt_id:
                custom_prompt = prompt.get("prompt")
                break

    if body.strategy == "ai":
        script, ai_status = generate_strategy_ai(ctx, custom_prompt=custom_prompt)
    elif body.strategy == "hybrid":
        script, ai_status = generate_strategy_hybrid(ctx, custom_prompt=custom_prompt)
    else:
        script = generate_strategy_template(ctx)
        ai_status = "template"

    return {
        "ok": True,
        "subject": build_tk_email_subject(ctx),
        "body": script,
        "script": script,
        "handle": ctx.get("handle", ""),
        "product_key": ctx.get("product_key", "all"),
        "product_asset": product_asset,
        "commission": int(ctx.get("commission") or 20),
        "strategy": body.strategy,
        "ai_status": ai_status,
        "context_used": {
            "bio_excerpt": ctx.get("bio_excerpt", ""),
            "video_title": ctx.get("video_title", ""),
            "matched_keywords": ctx.get("matched_keywords", ""),
            "recommendation_reason": ctx.get("recommendation_reason", ""),
            "product_label": ctx.get("product_label", ""),
            "product_asset_name": ctx.get("product_asset_name", ""),
            "product_sku_code": ctx.get("product_sku_code", ""),
            "product_selling_points": ctx.get("product_selling_points", ""),
            "followers_count": ctx.get("followers_count", ""),
            "personalized_interest": ctx.get("personalized_interest", ""),
        },
    }


@router.post("/draft")
def create_draft(body: DraftIn, request: Request, db: Session = Depends(get_db)) -> dict:
    department_code = current_department_code(request)
    current_user = getattr(request.state, "current_user", None) or {}
    creator = _resolve_creator(db, body.creator_id, department_code)
    require_creator_lock(db, creator_id=str(creator.id), user=current_user)
    template = None
    rendered_subject = body.subject
    rendered_body = body.body
    rendered_context: dict[str, Any] = {}

    if body.template_id or (rendered_subject is None or rendered_body is None):
        template = pick_template(db, creator, template_id=body.template_id)
        if template is None:
            raise HTTPException(status_code=400, detail="no template available")
        rendered = render_template(
            template,
            creator,
            sender_name=body.sender_name,
            sender_signature=body.sender_signature,
        )
        rendered_subject = rendered_subject or rendered.subject
        rendered_body = rendered_body or rendered.body
        rendered_context = rendered.context

    to_email = body.to_email or creator.email
    if not to_email:
        raise HTTPException(
            status_code=400,
            detail="creator has no email and none was provided in the request",
        )

    draft = OutreachEmail(
        id=new_id("oem"),
        department_code=department_code or "cross_border",
        creator_id=creator.id,
        template_id=template.id if template else body.template_id,
        to_email=str(to_email),
        from_email=None,
        subject=rendered_subject or "",
        body=rendered_body or "",
        body_format=body.body_format or "plain",
        status="draft",
        review_required=1,
        auto_send=0,
        context_json=context_to_json(rendered_context) if rendered_context else None,
        ai_versions_json=json.dumps(body.ai_versions, ensure_ascii=False) if body.ai_versions else None,
        ai_tone=body.ai_tone,
        ai_language=body.ai_language,
        created_by=current_user.get("id") or current_user.get("identity"),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _email_to_dict(draft)


@router.patch("/draft/{draft_id}")
def patch_draft(draft_id: str, body: DraftPatch, request: Request, db: Session = Depends(get_db)) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    draft = db.get(OutreachEmail, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    if not row_in_department(draft, current_department_code(request)):
        raise HTTPException(status_code=404, detail="draft not found")
    if draft.status not in {"draft", "failed"}:
        raise HTTPException(status_code=400, detail=f"draft is {draft.status}, cannot edit")
    require_creator_lock(db, creator_id=str(draft.creator_id), user=current_user)
    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if key == "to_email" and value is not None:
            value = str(value)
        if key == "ai_versions":
            draft.ai_versions_json = json.dumps(value, ensure_ascii=False) if value else None
            continue
        setattr(draft, key, value)
    db.commit()
    db.refresh(draft)
    return _email_to_dict(draft)


@router.delete("/draft/{draft_id}")
def delete_draft(draft_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    draft = db.get(OutreachEmail, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    if not row_in_department(draft, current_department_code(request)):
        raise HTTPException(status_code=404, detail="draft not found")
    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="cannot delete a sent email; archive instead")
    draft.status = "cancelled"
    release_creator_lock_if_owned(db, creator_id=str(draft.creator_id), user=current_user, reason="draft_cancelled")
    db.commit()
    return {"ok": True}


@router.post("/drafts/{draft_id}/rollback")
def rollback_draft(
    draft_id: str,
    body: RollbackIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Copy the subject/body from a historical email (same creator) into the
    current draft. Links the two rows via ``parent_email_id`` so the history
    sidebar can render a lineage."""
    current_user = getattr(request.state, "current_user", None) or {}
    draft = db.get(OutreachEmail, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    if not row_in_department(draft, current_department_code(request)):
        raise HTTPException(status_code=404, detail="draft not found")
    if draft.status not in {"draft", "failed"}:
        raise HTTPException(status_code=400, detail=f"draft is {draft.status}, cannot edit")
    require_creator_lock(db, creator_id=str(draft.creator_id), user=current_user)

    source = db.get(OutreachEmail, body.target_email_id)
    if source is None or source.creator_id != draft.creator_id:
        raise HTTPException(status_code=404, detail="target email not found for this creator")
    if not row_in_department(source, current_department_code(request)):
        raise HTTPException(status_code=404, detail="target email not found for this creator")

    draft.subject = source.subject
    draft.body = source.body
    draft.body_format = source.body_format or "plain"
    draft.parent_email_id = source.id
    db.commit()
    db.refresh(draft)
    return _email_to_dict(draft)


@router.post("/send/{draft_id}")
def send_draft(draft_id: str, body: SendIn, request: Request, db: Session = Depends(get_db)) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true to send")
    current_user = getattr(request.state, "current_user", None) or {}
    draft = db.get(OutreachEmail, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    if not row_in_department(draft, current_department_code(request)):
        raise HTTPException(status_code=404, detail="draft not found")
    if draft.status == "sent":
        raise HTTPException(status_code=400, detail="email already sent")
    if not draft.to_email or "@" not in draft.to_email:
        raise HTTPException(status_code=400, detail=f"invalid recipient: {draft.to_email!r}")

    require_creator_lock(db, creator_id=str(draft.creator_id), user=current_user)
    if not draft.created_by:
        draft.created_by = current_user.get("id") or current_user.get("identity")
    draft.status = "queued"
    db.commit()

    try:
        result = gmail_service.send_email(
            to_email=draft.to_email,
            subject=draft.subject,
            body=draft.body,
            body_format=draft.body_format,
            from_account_id=body.from_account_id,
            **_gmail_scope(current_user),
        )
    except gmail_service.GmailNotConfiguredError as exc:
        draft.status = "failed"
        draft.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except gmail_service.GmailNotAuthorizedError as exc:
        draft.status = "failed"
        draft.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        draft.status = "failed"
        draft.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    draft.status = "sent"
    draft.sent_at = datetime.utcnow()
    draft.gmail_message_id = result.get("message_id")
    draft.gmail_thread_id = result.get("thread_id")
    draft.from_email = result.get("from_email") or draft.from_email
    draft.error_message = None

    if body.update_creator_status:
        creator = db.get(Creator, draft.creator_id)
        if creator is not None:
            create_outreach_event(
                db,
                creator,
                event_type="sent",
                actor_user_id=current_user.get("id") or current_user.get("identity"),
                owner_bd=creator.owner_bd,
                metadata={"outreach_email_id": draft.id, "gmail_message_id": draft.gmail_message_id},
            )
        elif str(draft.creator_id).isdigit():
            try:
                remote_creators.patch(draft.creator_id, current_status="\u5f85\u56de\u590d")
            except RemoteRepoError:
                # The email has already been accepted by Gmail. Do not fail the
                # send response only because the optional status sync failed.
                pass

    release_creator_lock_if_owned(db, creator_id=str(draft.creator_id), user=current_user, reason="sent")
    db.commit()
    db.refresh(draft)
    return _email_to_dict(draft)


@router.get("/archive")
def list_outreach_archive(
    request: Request,
    creator_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    from_email: str | None = Query(default=None),
    to_email: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    department_code = current_department_code(request)
    filters = [OutreachEmail.status == "sent"]
    where_department = department_where(OutreachEmail, department_code)
    if where_department is not None:
        filters.append(where_department)
    if creator_id:
        filters.append(OutreachEmail.creator_id == creator_id)
    if from_email:
        filters.append(OutreachEmail.from_email.ilike(f"%{from_email.strip()}%"))
    if to_email:
        filters.append(OutreachEmail.to_email.ilike(f"%{to_email.strip()}%"))
    if q and q.strip():
        needle = f"%{q.strip()}%"
        filters.append(
            or_(
                OutreachEmail.subject.ilike(needle),
                OutreachEmail.body.ilike(needle),
                OutreachEmail.to_email.ilike(needle),
                OutreachEmail.from_email.ilike(needle),
                OutreachEmail.creator_id.ilike(needle),
            )
        )
    sent_at = func.coalesce(OutreachEmail.sent_at, OutreachEmail.created_at)
    start = _parse_archive_datetime(date_from, "date_from")
    end = _parse_archive_datetime(date_to, "date_to")
    if start is not None:
        filters.append(sent_at >= start)
    if end is not None:
        filters.append(sent_at <= end)

    total = int(db.scalar(select(func.count()).select_from(OutreachEmail).where(*filters)) or 0)
    rows = list(
        db.scalars(
            select(OutreachEmail)
            .where(*filters)
            .order_by(sent_at.desc(), OutreachEmail.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    creators = _creator_summary_map(db, [str(row.creator_id) for row in rows], department_code)
    return {
        "ok": True,
        "total": total,
        "items": [_archive_item_to_dict(row, creators.get(str(row.creator_id))) for row in rows],
    }


@router.get("/archive/{email_id}")
def get_outreach_archive_email(email_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    department_code = current_department_code(request)
    email = db.get(OutreachEmail, email_id)
    if email is None or email.status != "sent":
        raise HTTPException(status_code=404, detail="archived email not found")
    if not row_in_department(email, department_code):
        raise HTTPException(status_code=404, detail="archived email not found")
    creators = _creator_summary_map(db, [str(email.creator_id)], department_code)
    return {"ok": True, "item": _archive_detail_to_dict(email, creators.get(str(email.creator_id)))}


@router.get("/drafts")
def list_drafts(
    request: Request,
    status: str | None = Query(default=None),
    creator_id: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    filters = []
    where_department = department_where(OutreachEmail, current_department_code(request))
    if where_department is not None:
        filters.append(where_department)
    if status:
        filters.append(OutreachEmail.status == status)
    if creator_id:
        filters.append(OutreachEmail.creator_id == creator_id)
    total = int(db.scalar(select(func.count()).select_from(OutreachEmail).where(*filters)) or 0)
    q = select(OutreachEmail).where(*filters).order_by(OutreachEmail.created_at.desc()).offset(offset).limit(limit)
    rows = list(db.scalars(q).all())
    return {"ok": True, "total": total, "items": [_email_to_dict(r) for r in rows]}


@router.get("/history/{creator_id}")
def email_history(
    creator_id: str,
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    filters = [OutreachEmail.creator_id == creator_id]
    where_department = department_where(OutreachEmail, current_department_code(request))
    if where_department is not None:
        filters.append(where_department)
    total = int(db.scalar(select(func.count()).select_from(OutreachEmail).where(*filters)) or 0)
    q = (
        select(OutreachEmail)
        .where(*filters)
        .order_by(OutreachEmail.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = list(db.scalars(q).all())
    return {"ok": True, "total": total, "items": [_email_to_dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Gmail OAuth surface
# ---------------------------------------------------------------------------


def _gmail_user_scope(current_user: dict[str, Any] | None) -> str | None:
    """Every logged-in account uses its own Gmail authorization."""
    current_user = current_user or {}
    return current_user.get("id")


def _gmail_scope(current_user: dict[str, Any] | None) -> dict[str, Any]:
    current_user = current_user or {}
    gmail_service.claim_matching_unowned_account(
        user_id=current_user.get("id"),
        email=current_user.get("email"),
        department_code=current_user.get("department_code"),
    )
    return {
        "user_id": current_user.get("id"),
        "department_code": current_user.get("department_code"),
        "include_shared": False,
    }


def _gmail_save_owner(current_user: dict[str, Any] | None) -> dict[str, str | None]:
    current_user = current_user or {}
    return {
        "user_id": current_user.get("id"),
        "department_code": current_user.get("department_code"),
    }


def _gmail_feedback_redirect(
    state: str | None,
    *,
    status: str,
    msg: str | None = None,
    email: str | None = None,
) -> RedirectResponse:
    from urllib.parse import quote_plus

    target = gmail_service.decode_state_return_to(state) or "/portal/"
    sep = "&" if "?" in target else "?"
    parts = [f"gmail={quote_plus(status)}"]
    if msg:
        parts.append(f"msg={quote_plus(msg)}")
    if email:
        parts.append(f"email={quote_plus(email)}")
    return RedirectResponse(url=f"{target}{sep}{'&'.join(parts)}", status_code=302)


@router.get("/gmail/status")
def gmail_status(request: Request) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    request_origin = (request.headers.get("origin") or "").rstrip("/") or None
    gmail_scope = _gmail_scope(current_user)
    snapshot = gmail_service.status(**gmail_scope)
    origins = snapshot.get("accounts") and gmail_service.public_javascript_origins() or gmail_service.public_javascript_origins()
    snapshot["current_origin"] = request_origin
    snapshot["origin_match"] = bool(request_origin and origins and request_origin in origins)
    snapshot["javascript_origins"] = origins
    if request_origin:
        snapshot["redirect_uri_callback"] = (
            f"{request_origin}/api/local/outreach/gmail/callback"
        )
    snapshot["diagnostics"] = gmail_service.diagnose(request_origin, **gmail_scope)
    return {"ok": True, **snapshot}


@router.get("/gmail/client-info")
def gmail_client_info(request: Request) -> dict:
    """Public info for the frontend to initialize Google Identity Services.

    Returns ONLY the ``client_id`` and OAuth scopes — never the
    ``client_secret``. The secret stays on the server and is only used in
    the ``/gmail/exchange`` step when swapping the popup-issued code for
    a real refresh token.
    """
    client_id = gmail_service.public_client_id()
    if not client_id:
        raise HTTPException(status_code=400, detail="Gmail OAuth client not configured")
    request_origin = (request.headers.get("origin") or "").rstrip("/") or None
    origins = gmail_service.public_javascript_origins()
    gmail_scope = _gmail_scope(getattr(request.state, "current_user", None))
    return {
        "ok": True,
        "client_id": client_id,
        "scopes": gmail_service.SCOPES,
        "javascript_origins": origins,
        "current_origin": request_origin,
        "origin_match": bool(request_origin and origins and request_origin in origins),
        "diagnostics": gmail_service.diagnose(request_origin, **gmail_scope),
    }


class GmailExchangeIn(BaseModel):
    code: str
    # GIS popup mode issues the code against the page origin, for example
    # ``https://usx9.us``. Older builds sent the legacy literal
    # ``postmessage``; the route below normalizes that using the Origin
    # header so cached frontend code can still complete authorization.
    redirect_uri: str | None = None


@router.post("/gmail/exchange")
def gmail_exchange(body: GmailExchangeIn, request: Request) -> JSONResponse:
    """Exchange a popup-issued OAuth authorization code for tokens and
    persist a ``GmailAccount`` row. Used by the frontend after a successful
    Google Identity Services ``initCodeClient`` callback."""
    current_user = getattr(request.state, "current_user", None)
    if not current_user:
        raise HTTPException(status_code=401, detail="login required before connecting Gmail")
    try:
        redirect_uri = _gis_exchange_redirect_uri(body.redirect_uri, request)
        owner = _gmail_save_owner(current_user)
        account = gmail_service.handle_oauth_callback(
            body.code,
            redirect_uri=redirect_uri,
            user_id=owner.get("user_id"),
            department_code=owner.get("department_code"),
        )
    except gmail_service.GmailNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except gmail_service.GmailNotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "account": account, "user": current_user})


def _gis_exchange_redirect_uri(raw_redirect_uri: str | None, request: Request) -> str | None:
    """Return the redirect_uri expected by Google's GIS popup code flow."""
    if raw_redirect_uri and raw_redirect_uri != "postmessage":
        return raw_redirect_uri
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("/gmail/accounts")
def gmail_list_accounts(request: Request) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    rows = gmail_service.list_accounts(**_gmail_scope(current_user))
    return {"ok": True, "items": rows}


@router.delete("/gmail/accounts/{account_id}")
def gmail_remove_account(account_id: str, request: Request) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    if not gmail_service.remove_account(account_id, user_id=current_user.get("id"), allow_all=False):
        raise HTTPException(status_code=404, detail="account not found")
    return {"ok": True}


@router.post("/gmail/accounts/{account_id}/default")
def gmail_set_default(account_id: str, request: Request) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    if not gmail_service.set_default_account(account_id, user_id=current_user.get("id"), allow_all=False):
        raise HTTPException(status_code=404, detail="account not found or inactive")
    return {"ok": True}


@router.get("/gmail/auth-url")
def gmail_auth_url(
    request: Request,
    label: str | None = Query(default=None),
    return_to: str | None = Query(default=None),
) -> dict:
    current_user = getattr(request.state, "current_user", None)
    if not current_user:
        raise HTTPException(status_code=401, detail="login required before connecting Gmail")
    try:
        owner = _gmail_save_owner(current_user)
        info = gmail_service.build_auth_url(
            label=label,
            return_to=return_to,
            user_id=owner.get("user_id"),
            department_code=owner.get("department_code"),
            owner_verified=True,
        )
    except gmail_service.GmailNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **info}


@router.get("/gmail/connect")
def gmail_connect(
    request: Request,
    label: str | None = Query(default=None),
    return_to: str | None = Query(default=None),
):
    """Direct-link entry: a plain <a href> can point here. The user clicks
    once → server builds the Google auth URL → 302 redirects the browser to
    Google. No JS fetch round-trip, no toast on errors.

    ``return_to`` is passed through to the auth state so the callback can
    bounce the browser back to the exact SPA path that initiated the flow
    (avoids landing on the wrong workspace when the backend port shifted).
    """
    current_user = getattr(request.state, "current_user", None)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    try:
        owner = _gmail_save_owner(current_user)
        info = gmail_service.build_auth_url(
            label=label,
            return_to=return_to,
            user_id=owner.get("user_id"),
            department_code=owner.get("department_code"),
            owner_verified=True,
        )
    except gmail_service.GmailNotConfiguredError as exc:
        # Render a real error page instead of returning a JSON 400 — the
        # browser is here directly, not via fetch().
        from html import escape

        body = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Gmail 未配置</title>"
            "<style>body{background:#0f1115;color:#e7eaf0;font:14px/1.6 system-ui;"
            "padding:32px;max-width:680px;margin:0 auto}"
            "code{background:#1f242c;padding:2px 6px;border-radius:4px}"
            "a{color:#fbbf24}h2{color:#fbbf24}</style></head><body>"
            "<h2>Gmail 未配置</h2>"
            f"<p>{escape(str(exc))}</p>"
            "<p>请按 <code>backend/README_OUTREACH.md</code> 把 Google OAuth "
            "客户端 JSON 放到 <code>data/gmail_client_secret.json</code>，再点连接。</p>"
            "<p><a href='/portal/'>← 返回控制台</a></p>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=400)
    return RedirectResponse(url=info["auth_url"], status_code=302)


@router.get("/gmail/callback")
def gmail_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Google redirects the browser here after consent.

    On success/failure we 302 back to the originating SPA path with a
    query flag so the frontend can show a concrete binding result.
    """
    if error:
        return _gmail_feedback_redirect(state, status="error", msg=error)
    if not code:
        return _gmail_feedback_redirect(state, status="error", msg="missing_code")
    if not state:
        return _gmail_feedback_redirect(state, status="error", msg="missing_state")
    state_payload = gmail_service.decode_state_payload(state, verify_signature=True)
    if not state_payload:
        return _gmail_feedback_redirect(state, status="error", msg="invalid_state")

    current_user = getattr(request.state, "current_user", None)
    state_owner = gmail_service.decode_state_owner(state)
    has_verified_state_owner = bool(state_owner.get("owner_verified"))
    if (
        current_user
        and state_owner.get("user_id")
        and state_owner.get("user_id") != current_user.get("id")
    ):
        return _gmail_feedback_redirect(state, status="error", msg="state_user_mismatch")
    if not current_user and not has_verified_state_owner:
        return RedirectResponse(url="/login?gmail=login_required", status_code=302)

    try:
        owner = _gmail_save_owner(current_user) if current_user else state_owner
        result = gmail_service.handle_oauth_callback(
            code,
            state=state,
            user_id=owner.get("user_id"),
            department_code=owner.get("department_code"),
        )
    except gmail_service.GmailNotConfiguredError as exc:
        return _gmail_feedback_redirect(state, status="error", msg=str(exc))
    except gmail_service.GmailNotAuthorizedError as exc:
        return _gmail_feedback_redirect(state, status="error", msg=str(exc))
    except Exception as exc:
        return _gmail_feedback_redirect(state, status="error", msg=str(exc))

    email = result.get("email") or ""
    return _gmail_feedback_redirect(state, status="ok", email=email)


@router.post("/gmail/disconnect")
def gmail_disconnect(request: Request) -> dict:
    """Remove **all** authorized accounts. Use the per-account DELETE
    endpoint to remove just one."""
    current_user = getattr(request.state, "current_user", None) or {}
    gmail_service.revoke_all(user_id=current_user.get("id"))
    return {"ok": True}
