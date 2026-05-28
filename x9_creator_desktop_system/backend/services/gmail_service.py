"""Gmail OAuth2 + send service (multi-account).

Design notes
------------
* OAuth client secret comes from one of:
    - ``GMAIL_CLIENT_SECRET_PATH`` env var (path to JSON downloaded from
      Google Cloud Console).
    - ``data/gmail_client_secret.json`` (default fallback).
* Each authorized Gmail is stored in the ``gmail_accounts`` table as its
  own row with full credential JSON. Multiple BD members can each have
  their own account; outreach drafts choose which to send from.
* The legacy single-token file ``data/gmail_token.json`` (from earlier
  versions of this code) is auto-migrated into a row at startup.
* All ``google-*`` libraries are imported lazily so the rest of the app
  keeps working even before ``pip install``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from ..config import DATA_DIR, settings
from ..database.connection import SessionLocal
from ..models.gmail_account import GmailAccount
from ..utils.id_utils import new_id


logger = logging.getLogger(__name__)


SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

TOKEN_JSON_ENCRYPTED_PREFIX = "enc:v1:"
_TOKEN_CRYPTO_WARNING_EMITTED = False


class GmailNotConfiguredError(RuntimeError):
    """Raised when the OAuth client secret is missing on disk."""


class GmailNotAuthorizedError(RuntimeError):
    """Raised when no valid token has been issued yet."""


# ---------------------------------------------------------------------------
# Paths & config helpers
# ---------------------------------------------------------------------------


def _client_secret_path() -> Path:
    secret_env = os.getenv("GMAIL_CLIENT_SECRET_PATH")
    return Path(secret_env) if secret_env else (DATA_DIR / "gmail_client_secret.json")


def _legacy_token_path() -> Path:
    token_env = os.getenv("GMAIL_TOKEN_PATH")
    return Path(token_env) if token_env else (DATA_DIR / "gmail_token.json")


def _public_base_url() -> str | None:
    raw = os.getenv("X9_PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL")
    if not raw:
        return None
    return raw.rstrip("/")


def _redirect_uri() -> str:
    explicit = os.getenv("GMAIL_OAUTH_REDIRECT_URI")
    if explicit:
        return explicit
    public_base_url = _public_base_url()
    if public_base_url:
        return f"{public_base_url}/api/local/outreach/gmail/callback"
    return "https://usx9.us/api/local/outreach/gmail/callback"


def public_base_url() -> str | None:
    return _public_base_url()


# ---------------------------------------------------------------------------
# Lazy google-* imports
# ---------------------------------------------------------------------------


def _require_google() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        from google_auth_oauthlib.flow import Flow  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.errors import HttpError  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmailNotConfiguredError(
            "Gmail libraries not installed. Run: pip install "
            "google-auth google-auth-oauthlib google-api-python-client"
        ) from exc
    return Credentials, Request, Flow, build, HttpError


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Either a user-provided client_secret.json exists OR the maintainer
    has compiled in default OAuth client credentials via env vars."""
    if _client_secret_path().exists():
        return True
    return bool(settings.gmail_default_client_id and settings.gmail_default_client_secret)


def public_client_id() -> str | None:
    """Return ONLY the client_id (no secret) for the frontend to initialize
    Google Identity Services. Returns None if Gmail isn't configured."""
    try:
        config = _client_config()
    except GmailNotConfiguredError:
        return None
    section = config.get("installed") or config.get("web") or {}
    return section.get("client_id")


def public_javascript_origins() -> list[str]:
    """Return configured browser origins for GIS popup OAuth.

    This is public metadata from Google's OAuth client JSON; it lets the UI
    verify the current page origin against the configured live OAuth origins.
    """
    try:
        config = _client_config()
    except GmailNotConfiguredError:
        return []
    section = config.get("web") or config.get("installed") or {}
    origins = section.get("javascript_origins") or []
    return [str(origin) for origin in origins if origin]


def _client_config() -> dict:
    """Return a dict in the same shape as a Google ``client_secret.json``
    file. Prefers the user-provided file; falls back to embedded
    defaults compiled into ``settings``.

    Both "installed" (Desktop) and "web" (Web app) JSON shapes are passed
    through unchanged — google-auth-oauthlib's ``Flow.from_client_config``
    handles either."""
    path = _client_secret_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not (settings.gmail_default_client_id and settings.gmail_default_client_secret):
        raise GmailNotConfiguredError(
            "No Gmail OAuth client configured. Either drop your own JSON at "
            f"{path}, or set GMAIL_DEFAULT_CLIENT_ID + GMAIL_DEFAULT_CLIENT_SECRET "
            "env vars (and rebuild)."
        )
    # Build the synthetic client config dict. We use the "web" key here
    # (instead of "installed") because the Google Identity Services popup
    # flow expects a Web-type client; the same config still works for the
    # loopback redirect fallback.
    return {
        "web": {
            "client_id": settings.gmail_default_client_id,
            "client_secret": settings.gmail_default_client_secret,
            "project_id": settings.gmail_default_project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [_redirect_uri()],
        }
    }


def is_authorized(
    user_id: str | None = None,
    department_code: str | None = None,
    *,
    include_shared: bool = True,
) -> bool:
    """True iff at least one active account exists."""
    with SessionLocal() as session:
        q = _visible_accounts_query(
            session,
            user_id=user_id,
            department_code=department_code,
            include_shared=include_shared,
        )
        return q.count() > 0


def list_accounts(
    user_id: str | None = None,
    department_code: str | None = None,
    *,
    include_shared: bool = True,
) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        q = _visible_accounts_query(
            session,
            user_id=user_id,
            department_code=department_code,
            include_shared=include_shared,
        )
        rows = q.order_by(GmailAccount.is_default.desc(), GmailAccount.created_at.asc()).all()
        return [_account_to_dict(row) for row in rows]


def status(
    user_id: str | None = None,
    department_code: str | None = None,
    *,
    include_shared: bool = True,
) -> dict[str, Any]:
    """Snapshot for the UI status bar."""
    accounts = list_accounts(
        user_id=user_id,
        department_code=department_code,
        include_shared=include_shared,
    )
    has_user_secret = _client_secret_path().exists()
    has_embedded = bool(
        settings.gmail_default_client_id and settings.gmail_default_client_secret
    )
    return {
        "configured": has_user_secret or has_embedded,
        "configured_source": (
            "user_file" if has_user_secret else ("embedded" if has_embedded else "none")
        ),
        "authorized": bool(accounts),
        "client_secret_path": str(_client_secret_path()),
        "redirect_uri": _redirect_uri(),
        "public_base_url": public_base_url(),
        "accounts": accounts,
        "scopes": SCOPES,
        # Back-compat: keep ``email`` pointing at the default account
        # so older UI code reading ``status.email`` still works.
        "email": next(
            (a["email"] for a in accounts if a.get("is_default")),
            accounts[0]["email"] if accounts else None,
        ),
    }


def build_auth_url(
    state: str | None = None,
    label: str | None = None,
    return_to: str | None = None,
    user_id: str | None = None,
    department_code: str | None = None,
    owner_verified: bool = False,
) -> dict[str, str]:
    """Generate the Google OAuth consent URL.

    ``return_to`` is round-tripped through the OAuth state so the callback
    can redirect the browser back to the exact SPA path it came from
    — useful when the backend port is allocated dynamically and a
    hard-coded redirect target would land on the wrong workspace.
    """
    _, _, Flow, _, _ = _require_google()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
        autogenerate_code_verifier=False,
    )
    state_payload = {
        "label": label or "",
        "csrf": state or new_id("st"),
        "return_to": (return_to or "").strip()[:300],
        "user_id": user_id or "",
        "department_code": department_code or "",
        "owner_verified": bool(owner_verified),
    }
    state_payload["sig"] = _sign_state_payload(state_payload)
    state_str = base64.urlsafe_b64encode(
        json.dumps(state_payload, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
    auth_url, returned_state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state_str,
    )
    return {"auth_url": auth_url, "state": returned_state, "redirect_uri": _redirect_uri()}


def decode_state_return_to(state: str | None) -> str | None:
    payload = decode_state_payload(state, verify_signature=False)
    if not payload:
        return None
    target = (payload.get("return_to") or "").strip()
    # Defensive — only allow same-origin relative paths so attacker-controlled
    # states cannot redirect users off-site.
    if not target.startswith("/"):
        return None
    if target.startswith("//"):
        return None
    return target[:300]


def decode_state_owner(state: str | None) -> dict[str, Any]:
    payload = decode_state_payload(state, verify_signature=True)
    if not payload:
        return {"user_id": None, "department_code": None, "owner_verified": False}
    return {
        "user_id": (payload.get("user_id") or None),
        "department_code": (payload.get("department_code") or None),
        "owner_verified": bool(payload.get("owner_verified")),
    }


def decode_state_payload(
    state: str | None,
    *,
    verify_signature: bool = True,
) -> dict[str, Any] | None:
    if not state:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(state).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if verify_signature and payload.get("sig") != _sign_state_payload(payload):
        return None
    return payload


def _sign_state_payload(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k != "sig"}
    body = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    secret = (
        os.getenv("X9_OAUTH_STATE_SECRET")
        or settings.gmail_default_client_secret
        or settings.super_admin_password
        or "x9-local-oauth-state"
    )
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def handle_oauth_callback(
    code: str,
    state: str | None = None,
    redirect_uri: str | None = None,
    user_id: str | None = None,
    department_code: str | None = None,
) -> dict[str, Any]:
    """Exchange the OAuth code for tokens and persist as a new (or updated)
    ``gmail_accounts`` row keyed by email.

    The ``redirect_uri`` parameter is overridable so the same code path
    works for both flows:

    * Loopback redirect (Desktop client) — ``redirect_uri`` defaults to
      ``https://usx9.us/api/local/outreach/gmail/callback``.
    * Google Identity Services popup (Web client) — frontend passes
      ``"postmessage"`` here.
    """
    _, _, Flow, _, _ = _require_google()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=redirect_uri or _redirect_uri(),
        state=state or None,
        autogenerate_code_verifier=False,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    user_email = _fetch_user_email(creds) or "unknown@gmail.com"
    label = _decode_state_label(state)

    raw_token_json = creds.to_json() if hasattr(creds, "to_json") else json.dumps({})

    with SessionLocal() as session:
        account = _upsert_authorized_account(
            session,
            user_email=user_email,
            raw_token_json=raw_token_json,
            label=label,
            user_id=user_id,
            department_code=department_code,
        )
        session.commit()
        session.refresh(account)
        return _account_to_dict(account)

def remove_account(account_id: str, user_id: str | None = None, *, allow_all: bool = False) -> bool:
    """Soft-delete an account. Returns False if id was unknown."""
    with SessionLocal() as session:
        row = session.get(GmailAccount, account_id)
        if row is None:
            return False
        if not allow_all and (not user_id or row.user_id != user_id):
            return False
        was_default = bool(row.is_default)
        owner_id = row.user_id
        session.delete(row)
        if was_default:
            # Promote another active account to default if available
            q = session.query(GmailAccount).filter(GmailAccount.is_active == 1)
            if owner_id:
                q = q.filter(GmailAccount.user_id == owner_id)
            other = q.order_by(GmailAccount.created_at.asc()).first()
            if other is not None:
                other.is_default = 1
        session.commit()
    return True


def set_default_account(account_id: str, user_id: str | None = None, *, allow_all: bool = False) -> bool:
    with SessionLocal() as session:
        target = session.get(GmailAccount, account_id)
        if target is None or not target.is_active:
            return False
        if not allow_all and (not user_id or target.user_id != user_id):
            return False
        q = session.query(GmailAccount)
        if target.user_id:
            q = q.filter(GmailAccount.user_id == target.user_id)
        for row in q.all():
            row.is_default = 1 if row.id == target.id else 0
        session.commit()
    return True


def revoke_all(user_id: str | None = None) -> None:
    """Delete every stored token. Safe to call when none exist."""
    with SessionLocal() as session:
        q = session.query(GmailAccount)
        if user_id:
            q = q.filter(GmailAccount.user_id == user_id)
        q.delete()
        session.commit()


def claim_matching_unowned_account(
    *,
    user_id: str | None,
    email: str | None,
    department_code: str | None = None,
) -> None:
    """Attach a legacy shared Gmail row to the matching logged-in user.

    Older builds stored admin Gmail tokens with ``user_id=NULL``. The new
    per-account sending model should not expose those rows as shared, but
    if the Gmail address exactly matches the current local user's email we
    can safely migrate ownership without forcing a fresh OAuth round-trip.
    """
    if not user_id or not email:
        return
    normalized_email = str(email).strip().lower()
    if not normalized_email:
        return
    with SessionLocal() as session:
        row = (
            session.query(GmailAccount)
            .filter(
                GmailAccount.email == normalized_email,
                GmailAccount.user_id.is_(None),
                GmailAccount.is_active == 1,
            )
            .first()
        )
        if row is None:
            return
        row.user_id = str(user_id)
        row.department_code = department_code
        has_default = (
            session.query(GmailAccount)
            .filter(
                GmailAccount.user_id == str(user_id),
                GmailAccount.is_active == 1,
                GmailAccount.is_default == 1,
            )
            .count()
            > 0
        )
        if not has_default:
            row.is_default = 1
        session.commit()


def send_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    body_format: str = "plain",
    from_account_id: str | None = None,
    from_email: str | None = None,
    user_id: str | None = None,
    department_code: str | None = None,
    include_shared: bool = True,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Send a single email via Gmail API.

    Selection priority for the sender account:
      1. ``from_account_id`` (explicit)
      2. ``from_email`` matches an account
      3. the row marked ``is_default=1``
      4. any active row
    Raises :class:`GmailNotAuthorizedError` if no usable account exists.
    """
    if not to_email or "@" not in to_email:
        raise ValueError(f"invalid recipient: {to_email!r}")

    Credentials, Request, _Flow, build, HttpError = _require_google()

    with SessionLocal() as session:
        account = _resolve_account(
            session,
            account_id=from_account_id,
            email=from_email,
            user_id=user_id,
            department_code=department_code,
            include_shared=include_shared,
        )
        if account is None:
            raise GmailNotAuthorizedError(
                "No authorized Gmail account. Connect one in the outreach modal first."
            )

        stored_token_json = account.token_json or "{}"
        raw_token_json = _token_json_from_storage(stored_token_json)
        creds = Credentials.from_authorized_user_info(json.loads(raw_token_json), scopes=SCOPES)
        if not _token_json_is_encrypted(stored_token_json) and _token_cipher() is not None:
            account.token_json = _token_json_to_storage(raw_token_json)
        if not creds.valid and getattr(creds, "refresh_token", None):
            creds.refresh(Request())
            account.token_json = _token_json_to_storage(creds.to_json())

        sender = account.email
        raw = _build_mime_message(
            to_email=to_email,
            subject=subject,
            body=body,
            body_format=body_format,
            from_email=sender,
            reply_to=reply_to,
        )

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        try:
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        except HttpError as exc:
            raise RuntimeError(f"Gmail send failed: {exc}") from exc

        account.last_used_at = datetime.utcnow()
        session.commit()

        return {
            "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
            "from_email": sender,
            "from_account_id": account.id,
        }


# ---------------------------------------------------------------------------
# Migration: bring the legacy single-file token into the new table
# ---------------------------------------------------------------------------


def migrate_legacy_token_if_present() -> None:
    """If the old ``data/gmail_token.json`` exists and the table is empty,
    move it into a ``GmailAccount`` row marked ``is_default=1``."""
    legacy = _legacy_token_path()
    if not legacy.exists():
        return
    try:
        payload = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover
        logger.warning("legacy gmail token unreadable: %s", exc)
        return

    email = payload.get("user_email") or payload.get("email") or "legacy@gmail.com"

    with SessionLocal() as session:
        if session.query(GmailAccount).filter(GmailAccount.email == email).count() > 0:
            return
        existing_count = session.query(GmailAccount).count()
        row = GmailAccount(
            id=new_id("gma"),
            user_id=None,
            department_code=None,
            email=email,
            display_name=email.split("@")[0],
            label="legacy",
            token_json=_token_json_to_storage(json.dumps(payload, ensure_ascii=False)),
            is_default=1 if existing_count == 0 else 0,
            is_active=1,
        )
        session.add(row)
        session.commit()
    # Rename the file so we don't migrate twice
    try:
        legacy.rename(legacy.with_suffix(".json.migrated"))
    except OSError:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_authorized_account(
    session: Session,
    *,
    user_email: str,
    raw_token_json: str,
    label: str | None,
    user_id: str | None,
    department_code: str | None,
) -> GmailAccount:
    normalized_email = (user_email or "").strip().lower() or "unknown@gmail.com"
    existing = session.query(GmailAccount).filter(GmailAccount.email == normalized_email).first()
    if existing is not None and existing.user_id and existing.user_id != user_id:
        raise GmailNotAuthorizedError("This Gmail account is already linked to another local user.")
    if existing is not None and existing.user_id and not user_id:
        raise GmailNotAuthorizedError("Login is required before connecting this Gmail account.")

    stored_token_json = _token_json_to_storage(raw_token_json)
    if existing is None:
        existing = GmailAccount(
            id=new_id("gma"),
            user_id=user_id,
            department_code=department_code,
            email=normalized_email,
            display_name=normalized_email.split("@")[0],
            label=label,
            token_json=stored_token_json,
            is_default=0,
            is_active=1,
        )
        session.add(existing)
    else:
        existing.token_json = stored_token_json
        existing.is_active = 1
        existing.user_id = user_id or existing.user_id
        existing.department_code = department_code or existing.department_code
        if label:
            existing.label = label

    default_q = session.query(GmailAccount).filter(GmailAccount.is_active == 1)
    if user_id:
        default_q = default_q.filter(GmailAccount.user_id == user_id)
    if default_q.filter(GmailAccount.is_default == 1).count() == 0:
        existing.is_default = 1
    return existing


def _token_json_is_encrypted(stored_token_json: str | None) -> bool:
    return bool(stored_token_json and stored_token_json.startswith(TOKEN_JSON_ENCRYPTED_PREFIX))


def _token_json_to_storage(raw_token_json: str) -> str:
    cipher = _token_cipher()
    if cipher is None:
        _warn_plaintext_token_storage_once()
        return raw_token_json
    encrypted = cipher.encrypt(raw_token_json.encode("utf-8")).decode("ascii")
    return f"{TOKEN_JSON_ENCRYPTED_PREFIX}{encrypted}"


def _token_json_from_storage(stored_token_json: str) -> str:
    if not _token_json_is_encrypted(stored_token_json):
        return stored_token_json
    cipher = _token_cipher()
    if cipher is None:
        raise GmailNotAuthorizedError(
            "Stored Gmail token is encrypted, but the token encryption key or dependency is unavailable."
        )
    encrypted = stored_token_json[len(TOKEN_JSON_ENCRYPTED_PREFIX):]
    try:
        return cipher.decrypt(encrypted.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise GmailNotAuthorizedError("Stored Gmail token cannot be decrypted. Reconnect Gmail.") from exc


def _token_cipher() -> Any | None:
    material = (
        os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY")
        or os.getenv("X9_TOKEN_ENCRYPTION_KEY")
        or settings.gmail_token_encryption_key
        or os.getenv("X9_OAUTH_STATE_SECRET")
        or settings.gmail_default_client_secret
    )
    if not material:
        return None
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())
    return Fernet(key)


def _warn_plaintext_token_storage_once() -> None:
    global _TOKEN_CRYPTO_WARNING_EMITTED
    if _TOKEN_CRYPTO_WARNING_EMITTED:
        return
    _TOKEN_CRYPTO_WARNING_EMITTED = True
    logger.warning(
        "Gmail tokens are being stored without field encryption. Install cryptography and set GMAIL_TOKEN_ENCRYPTION_KEY."
    )


def _visible_accounts_query(
    session: Session,
    *,
    user_id: str | None = None,
    department_code: str | None = None,
    include_shared: bool = True,
):
    q = session.query(GmailAccount).filter(GmailAccount.is_active == 1)
    if not user_id and not department_code:
        return q if include_shared else q.filter(false())

    clauses = []
    if user_id:
        clauses.append(GmailAccount.user_id == user_id)

    if include_shared:
        shared_clause = GmailAccount.user_id.is_(None)
        if department_code:
            shared_clause = and_(
                shared_clause,
                or_(GmailAccount.department_code.is_(None), GmailAccount.department_code == department_code),
            )
        clauses.append(shared_clause)
    elif department_code and not user_id:
        clauses.append(GmailAccount.department_code == department_code)

    return q.filter(or_(*clauses)) if clauses else q


def _account_visible_to(
    account: GmailAccount,
    *,
    user_id: str | None = None,
    department_code: str | None = None,
    include_shared: bool = True,
) -> bool:
    if not user_id and not department_code:
        return include_shared
    if user_id and account.user_id == user_id:
        return True
    if include_shared and account.user_id is None:
        if not department_code:
            return True
        return account.department_code in {None, department_code}
    return False


def _resolve_account(
    session: Session,
    *,
    account_id: str | None,
    email: str | None,
    user_id: str | None = None,
    department_code: str | None = None,
    include_shared: bool = True,
) -> GmailAccount | None:
    if account_id:
        row = session.get(GmailAccount, account_id)
        if row is not None and row.is_active and _account_visible_to(
            row,
            user_id=user_id,
            department_code=department_code,
            include_shared=include_shared,
        ):
            return row
    if email:
        q = _visible_accounts_query(
            session,
            user_id=user_id,
            department_code=department_code,
            include_shared=include_shared,
        ).filter(GmailAccount.email == email)
        row = q.first()
        if row is not None and row.is_active:
            return row
    q = _visible_accounts_query(
        session,
        user_id=user_id,
        department_code=department_code,
        include_shared=include_shared,
    )
    row = q.filter(GmailAccount.is_default == 1).first()
    if row is not None:
        return row
    return q.order_by(GmailAccount.created_at.asc()).first()


def _decode_state_label(state: str | None) -> str | None:
    if not state:
        return None
    try:
        decoded = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
        return payload.get("label") or None
    except Exception:
        return None


def _account_to_dict(account: GmailAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "user_id": account.user_id,
        "department_code": account.department_code,
        "email": account.email,
        "display_name": account.display_name,
        "label": account.label,
        "is_default": bool(account.is_default),
        "is_active": bool(account.is_active),
        "last_used_at": _iso_or_none(account.last_used_at),
        "created_at": _iso_or_none(account.created_at),
    }


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_mime_message(
    *,
    to_email: str,
    subject: str,
    body: str,
    body_format: str,
    from_email: str,
    reply_to: str | None = None,
) -> str:
    if body_format == "html":
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain", "utf-8"))
        message.attach(MIMEText(body, "html", "utf-8"))
    else:
        message = MIMEText(body or "", "plain", "utf-8")
    message["To"] = to_email
    message["From"] = from_email
    message["Subject"] = subject or "(no subject)"
    if reply_to:
        message["Reply-To"] = reply_to
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def _fetch_user_email(creds: Any) -> str | None:
    try:
        _Credentials, Request, _Flow, build, _HttpError = _require_google()
        if not creds.valid and getattr(creds, "refresh_token", None):
            creds.refresh(Request())
        service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = service.userinfo().get().execute()
        return info.get("email")
    except Exception as exc:  # pragma: no cover
        logger.debug("could not fetch user email: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def diagnose(
    request_origin: str | None = None,
    *,
    user_id: str | None = None,
    department_code: str | None = None,
    include_shared: bool = True,
) -> list[dict[str, str]]:
    """Return structured diagnostics about the Gmail OAuth setup.

    The frontend renders these so a non-engineer can see WHY the connect
    button isn't working: missing client id, current page origin not
    registered in Google Cloud Console, legacy token leftover, etc. Each
    entry has a level (info/warn/error), a stable ``code`` for i18n, a
    human message, and an actionable ``action`` hint.
    """
    out: list[dict[str, str]] = []

    try:
        _require_google()
    except GmailNotConfiguredError as exc:
        out.append({
            "level": "error",
            "code": "gmail_libraries_missing",
            "message": "Gmail OAuth 依赖未安装。",
            "action": str(exc),
        })

    if not _client_secret_path().exists():
        if not (settings.gmail_default_client_id and settings.gmail_default_client_secret):
            out.append({
                "level": "error",
                "code": "client_id_missing",
                "message": "未找到 OAuth 客户端凭证。",
                "action": (
                    "把 Google Cloud Console 的 OAuth Web client JSON 重命名为 "
                    "gmail_client_secret.json 放到 data/ 目录,或在环境变量里设置 "
                    "GMAIL_DEFAULT_CLIENT_ID + GMAIL_DEFAULT_CLIENT_SECRET 后重启后端。"
                ),
            })
            return out
        out.append({
            "level": "info",
            "code": "embedded_credentials_only",
            "message": "使用打包到环境变量里的默认 OAuth 客户端。",
            "action": "如需自定义,请把 data/gmail_client_secret.json 放上去 — 它优先于环境变量。",
        })

    origins = public_javascript_origins()
    if request_origin and origins and request_origin not in origins:
        out.append({
            "level": "error",
            "code": "origin_not_registered",
            "message": (
                f"当前页面 origin {request_origin} 不在 Google OAuth 客户端的 "
                "Authorized JavaScript origins 列表里 (允许的有: "
                + ", ".join(origins) + ")。"
            ),
            "action": (
                "1) 在 Google Cloud Console 把当前 origin 登记进去 (推荐同时登 "
                "https://usx9.us); 2) 重新 "
                "打开页面;或 3) 直接点 '继续浏览器跳转' 走 loopback 流程。"
            ),
        })

    explicit_token_key = bool(
        os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY")
        or os.getenv("X9_TOKEN_ENCRYPTION_KEY")
        or settings.gmail_token_encryption_key
    )
    if _token_cipher() is None:
        out.append({
            "level": "warn",
            "code": "token_encryption_unavailable",
            "message": "Gmail token 字段级加密未启用。",
            "action": "安装 cryptography,设置 GMAIL_TOKEN_ENCRYPTION_KEY,然后重启后端并重新授权 Gmail。",
        })
    elif not explicit_token_key:
        out.append({
            "level": "warn",
            "code": "token_encryption_uses_fallback_key",
            "message": "Gmail token 已加密,但使用的是回退密钥材料。",
            "action": "生产环境请设置独立的 GMAIL_TOKEN_ENCRYPTION_KEY,避免 OAuth secret 轮换影响 token 解密。",
        })
    if _legacy_token_path().exists():
        out.append({
            "level": "warn",
            "code": "legacy_token_present",
            "message": f"检测到旧版单文件 token: {_legacy_token_path()}。",
            "action": "应用启动会自动迁移到 gmail_accounts 表;迁移完成后可删除旧文件。",
        })

    if not is_authorized(user_id=user_id, department_code=department_code, include_shared=include_shared):
        out.append({
            "level": "info",
            "code": "no_account_yet",
            "message": "尚未绑定任何 Gmail 账号。",
            "action": "在建联弹窗里点 '连接 Gmail' 完成首次授权。",
        })

    return out
