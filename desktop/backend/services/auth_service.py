from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database.connection import SessionLocal
from ..models.app_session import AppSession
from ..models.app_user import AppUser
from ..models.gmail_account import GmailAccount
from ..utils.id_utils import new_id
from .departments import DEFAULT_DEPARTMENT, DEPARTMENTS, department_slug, normalize_department_code


SESSION_COOKIE = "x9_session"
SESSION_DAYS = 14
SUPER_ADMIN_ROLE = "super_admin"
COMPANY_ADMIN_ROLE = "company_admin"
DEPARTMENT_ADMIN_ROLE = "department_admin"
DEPARTMENT_USER_ROLE = "department_user"
ADMIN_ROLES = {SUPER_ADMIN_ROLE, COMPANY_ADMIN_ROLE, DEPARTMENT_ADMIN_ROLE}
COMPANY_WIDE_ROLES = {SUPER_ADMIN_ROLE, COMPANY_ADMIN_ROLE}
USER_MANAGER_ROLES = {SUPER_ADMIN_ROLE, COMPANY_ADMIN_ROLE}
ROLES = {
    SUPER_ADMIN_ROLE,
    COMPANY_ADMIN_ROLE,
    DEPARTMENT_ADMIN_ROLE,
    DEPARTMENT_USER_ROLE,
    "admin",
    "bd",
    "viewer",
}
ACTIVE_STATUS = "active"
PENDING_STATUS = "pending"
REJECTED_STATUS = "rejected"
DISABLED_STATUS = "disabled"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")
LOCAL_EMAIL_DOMAIN = "local.x9"


class LoginNotAllowedError(RuntimeError):
    pass


def normalize_email(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    return value or None


def normalize_username(username: str | None) -> str:
    value = (username or "").strip().lower()
    if not USERNAME_RE.match(value):
        raise ValueError("username must be 3-40 characters: letters, numbers, dot, dash or underscore")
    return value


def normalize_role(role: str | None) -> str:
    raw = (role or "department_user").strip().lower()
    if raw in {"bd", "viewer"}:
        return DEPARTMENT_USER_ROLE
    if raw == "admin":
        return COMPANY_ADMIN_ROLE
    return raw if raw in ADMIN_ROLES | {DEPARTMENT_USER_ROLE} else DEPARTMENT_USER_ROLE


def role_needs_department(role: str | None) -> bool:
    return normalize_role(role) in {DEPARTMENT_ADMIN_ROLE, DEPARTMENT_USER_ROLE}


def actor_can_manage_users(actor: dict[str, Any]) -> bool:
    return normalize_role(actor.get("role")) in USER_MANAGER_ROLES


def actor_can_manage_role(actor: dict[str, Any], target_role: str | None) -> bool:
    actor_role = normalize_role(actor.get("role"))
    target = normalize_role(target_role)
    if actor_role == SUPER_ADMIN_ROLE:
        return True
    if actor_role == COMPANY_ADMIN_ROLE:
        return target in {DEPARTMENT_ADMIN_ROLE, DEPARTMENT_USER_ROLE}
    return False


def local_placeholder_email(username: str) -> str:
    return f"{username}@{LOCAL_EMAIL_DOMAIN}"


def public_email(email: str | None) -> str | None:
    value = normalize_email(email)
    if value and value.endswith(f"@{LOCAL_EMAIL_DOMAIN}"):
        return None
    return value


def hash_password(password: str) -> str:
    if len(password or "") < 6:
        raise ValueError("password must be at least 6 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        [
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        scheme, raw_iterations, raw_salt, raw_digest = stored_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(raw_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(raw_digest.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)


def seed_admin_users() -> None:
    with SessionLocal() as session:
        _ensure_super_admin(session)
        _ensure_legacy_admin_emails(session)
        session.commit()


def _ensure_super_admin(session: Session) -> None:
    try:
        username = normalize_username(settings.super_admin_username or "superadmin")
    except ValueError:
        username = "superadmin"
    password = settings.super_admin_password or "X9@2026"
    must_change = 1 if os.getenv("X9_SUPER_ADMIN_PASSWORD") is None else 0
    user = session.scalar(select(AppUser).where(AppUser.username == username))
    if user is None:
        user = session.scalar(select(AppUser).where(AppUser.role == SUPER_ADMIN_ROLE))
    if user is None:
        user = AppUser(
            id=new_id("user"),
            username=username,
            email=local_placeholder_email(username),
            display_name="Super Admin",
            role=SUPER_ADMIN_ROLE,
            department_code=None,
            approval_status=ACTIVE_STATUS,
            is_active=1,
            must_change_password=must_change,
            password_hash=hash_password(password),
            last_password_at=datetime.utcnow(),
            created_by="env:X9_SUPER_ADMIN_USERNAME",
            approved_by="system",
            approved_at=datetime.utcnow(),
        )
        session.add(user)
        return
    user.username = user.username or username
    user.email = user.email or local_placeholder_email(user.username or username)
    user.role = SUPER_ADMIN_ROLE
    user.department_code = None
    user.approval_status = ACTIVE_STATUS
    user.is_active = 1
    if not user.password_hash:
        user.password_hash = hash_password(password)
        user.must_change_password = must_change
        user.last_password_at = datetime.utcnow()


def _ensure_legacy_admin_emails(session: Session) -> None:
    emails = [normalize_email(e) for e in settings.admin_emails.replace(";", ",").split(",")]
    emails = [e for e in emails if e]
    for email in emails:
        existing = session.scalar(select(AppUser).where(AppUser.email == email))
        if existing:
            existing.role = COMPANY_ADMIN_ROLE
            existing.department_code = None
            existing.approval_status = ACTIVE_STATUS
            existing.is_active = 1
            if not existing.username:
                existing.username = _unique_username(session, email.split("@")[0])
            continue
        session.add(
            AppUser(
                id=new_id("user"),
                username=_unique_username(session, email.split("@")[0]),
                email=email,
                display_name=email.split("@")[0],
                role=COMPANY_ADMIN_ROLE,
                department_code=None,
                approval_status=ACTIVE_STATUS,
                is_active=1,
                must_change_password=1,
                created_by="env:X9_ADMIN_EMAILS",
                approved_by="system",
                approved_at=datetime.utcnow(),
            )
        )


def _unique_username(session: Session, seed: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", (seed or "user").strip().lower()).strip("._-")
    if len(cleaned) < 3:
        cleaned = f"{cleaned or 'user'}_x9"
    cleaned = cleaned[:36]
    candidate = cleaned
    i = 2
    while session.scalar(select(AppUser).where(AppUser.username == candidate)) is not None:
        suffix = f"_{i}"
        candidate = f"{cleaned[: 40 - len(suffix)]}{suffix}"
        i += 1
    return candidate


def user_to_dict(
    user: AppUser,
    gmail_account_id: str | None = None,
    *,
    entry_scope: str | None = None,
    department_code: str | None = None,
) -> dict[str, Any]:
    base_role = normalize_role(user.role)
    scope = entry_scope or ("admin" if base_role in ADMIN_ROLES else "workspace")
    dept = normalize_department_code(department_code or user.department_code, default=None)
    if scope == "admin" and base_role in COMPANY_WIDE_ROLES:
        role = base_role
        dept = None
    elif scope == "admin" and base_role == DEPARTMENT_ADMIN_ROLE:
        role = base_role
        dept = dept or DEFAULT_DEPARTMENT
    else:
        role = DEPARTMENT_USER_ROLE
        scope = "workspace"
        dept = dept or DEFAULT_DEPARTMENT
    visible_email = public_email(user.email)
    identity = visible_email or user.username or user.id
    return {
        "id": user.id,
        "username": user.username,
        "email": visible_email,
        "identity": identity,
        "display_name": user.display_name or user.username or (visible_email.split("@")[0] if visible_email else user.id),
        "role": role,
        "base_role": base_role,
        "entry_scope": scope,
        "department_code": dept,
        "department_slug": department_slug(dept) if dept else None,
        "department_name": DEPARTMENTS[dept]["name"] if dept else None,
        "approval_status": user.approval_status or ACTIVE_STATUS,
        "is_active": bool(user.is_active),
        "must_change_password": bool(user.must_change_password),
        "gmail_account_id": gmail_account_id,
        "can_manage_users": base_role in USER_MANAGER_ROLES,
        "can_create_company_admin": base_role == SUPER_ADMIN_ROLE,
        "can_reset_password": base_role == SUPER_ADMIN_ROLE,
    }


def list_users(db: Session, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(AppUser).order_by(AppUser.role.asc(), AppUser.username.asc())).all())
    actor_role = normalize_role(actor.get("role")) if actor else SUPER_ADMIN_ROLE
    if actor_role == COMPANY_ADMIN_ROLE:
        rows = [row for row in rows if normalize_role(row.role) in {DEPARTMENT_ADMIN_ROLE, DEPARTMENT_USER_ROLE}]
    elif actor_role not in {SUPER_ADMIN_ROLE, COMPANY_ADMIN_ROLE}:
        rows = []
    return [
        {
            **user_to_dict(row, entry_scope=("admin" if normalize_role(row.role) in ADMIN_ROLES else "workspace")),
            "role": normalize_role(row.role),
            "department_code": row.department_code,
        }
        for row in rows
    ]


def register_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    email: str | None = None,
    department_code: str | None = DEFAULT_DEPARTMENT,
) -> AppUser:
    username = normalize_username(username)
    email = normalize_email(email)
    if email and "@" not in email:
        raise ValueError("valid email is required")
    if _find_user(db, username):
        raise ValueError("username already exists")
    stored_email = email or local_placeholder_email(username)
    if db.scalar(select(AppUser).where(AppUser.email == stored_email)):
        raise ValueError("email already exists")
    user = AppUser(
        id=new_id("user"),
        username=username,
        email=stored_email,
        display_name=(display_name or "").strip() or username,
        role=DEPARTMENT_USER_ROLE,
        department_code=normalize_department_code(department_code, default=DEFAULT_DEPARTMENT),
        password_hash=hash_password(password),
        approval_status=PENDING_STATUS,
        is_active=0,
        must_change_password=0,
        last_password_at=datetime.utcnow(),
        created_by="self_register",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> tuple[str, dict[str, Any]]:
    user = _find_user(db, username)
    if user is None:
        raise LoginNotAllowedError("username or password is incorrect")
    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        raise LoginNotAllowedError("too many failed attempts; try again later")
    if not verify_password(password, user.password_hash):
        user.failed_login_count = int(user.failed_login_count or 0) + 1
        if user.failed_login_count >= 5:
            user.locked_until = now + timedelta(minutes=15)
        db.commit()
        raise LoginNotAllowedError("username or password is incorrect")
    if not _can_login(user):
        raise LoginNotAllowedError("account is waiting for admin approval or has been disabled")
    user.failed_login_count = 0
    user.locked_until = None
    return create_session_for_user(db, user)


def create_session_for_user(
    db: Session,
    user: AppUser,
    *,
    gmail_account_id: str | None = None,
    entry_scope: str | None = None,
    department_code: str | None = None,
) -> tuple[str, dict[str, Any]]:
    role = normalize_role(user.role)
    scope = "admin" if role in ADMIN_ROLES else "workspace"
    if entry_scope in {"admin", "workspace"} and role in ADMIN_ROLES:
        scope = entry_scope
    if role not in ADMIN_ROLES:
        scope = "workspace"
    dept = None if (scope == "admin" and role in COMPANY_WIDE_ROLES) else normalize_department_code(
        department_code or user.department_code,
        default=DEFAULT_DEPARTMENT,
    )
    token = secrets.token_urlsafe(48)
    session = AppSession(
        id=new_id("sess"),
        user_id=user.id,
        gmail_account_id=gmail_account_id,
        entry_scope=scope,
        department_code=dept,
        token_hash=_hash_token(token),
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
        last_seen_at=datetime.utcnow(),
    )
    user.last_login_at = datetime.utcnow()
    db.add(session)
    db.commit()
    return token, user_to_dict(user, gmail_account_id=gmail_account_id, entry_scope=scope, department_code=dept)


def upsert_user(
    db: Session,
    *,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
    role: str = "department_user",
    display_name: str | None = None,
    department_code: str | None = None,
    is_active: bool = True,
    approval_status: str | None = ACTIVE_STATUS,
    created_by: str | None = None,
) -> AppUser:
    email = normalize_email(email)
    username = normalize_username(username or (email.split("@")[0] if email else None))
    if email and "@" not in email:
        raise ValueError("valid email is required")
    role = normalize_role(role)
    stored_email = email or local_placeholder_email(username)
    user = _find_user(db, username) or db.scalar(select(AppUser).where(AppUser.email == stored_email))
    if user is None:
        user = AppUser(
            id=new_id("user"),
            username=username,
            email=stored_email,
            display_name=(display_name or "").strip() or username,
            role=role,
            department_code=normalize_department_code(department_code, default=DEFAULT_DEPARTMENT) if role_needs_department(role) else None,
            approval_status=approval_status or ACTIVE_STATUS,
            is_active=1 if is_active else 0,
            must_change_password=1 if password else 0,
            created_by=created_by,
            approved_by=created_by if (approval_status or ACTIVE_STATUS) == ACTIVE_STATUS else None,
            approved_at=datetime.utcnow() if (approval_status or ACTIVE_STATUS) == ACTIVE_STATUS else None,
        )
        db.add(user)
    else:
        user.username = user.username or username
        user.email = stored_email or user.email
        user.display_name = (display_name or "").strip() or user.display_name or username
        user.role = role
        user.department_code = normalize_department_code(department_code, default=DEFAULT_DEPARTMENT) if role_needs_department(role) else None
        user.is_active = 1 if is_active else 0
        if approval_status is not None:
            user.approval_status = approval_status
            if approval_status == ACTIVE_STATUS:
                user.approved_by = created_by or user.approved_by
                user.approved_at = user.approved_at or datetime.utcnow()
    if password:
        user.password_hash = hash_password(password)
        user.must_change_password = 1
        user.last_password_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def patch_user(
    db: Session,
    user_key: str,
    *,
    role: str | None = None,
    display_name: str | None = None,
    department_code: str | None = None,
    is_active: bool | None = None,
    approval_status: str | None = None,
) -> AppUser | None:
    user = _find_user(db, user_key)
    if user is None:
        return None
    if role is not None:
        user.role = normalize_role(role)
        if normalize_role(user.role) in COMPANY_WIDE_ROLES:
            user.department_code = None
        elif role_needs_department(user.role) and not user.department_code:
            user.department_code = DEFAULT_DEPARTMENT
    if department_code is not None:
        user.department_code = normalize_department_code(department_code, default=DEFAULT_DEPARTMENT) if role_needs_department(user.role) else None
    if display_name is not None:
        user.display_name = display_name.strip() or None
    if is_active is not None:
        user.is_active = 1 if is_active else 0
    if approval_status is not None:
        user.approval_status = approval_status
        if approval_status == ACTIVE_STATUS:
            user.is_active = 1
        elif approval_status in {REJECTED_STATUS, DISABLED_STATUS}:
            user.is_active = 0
    db.commit()
    db.refresh(user)
    return user


def approve_user(db: Session, user_key: str, admin_id: str | None) -> AppUser | None:
    user = _find_user(db, user_key)
    if user is None:
        return None
    user.approval_status = ACTIVE_STATUS
    user.is_active = 1
    user.approved_by = admin_id
    user.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def reject_user(db: Session, user_key: str, admin_id: str | None) -> AppUser | None:
    user = _find_user(db, user_key)
    if user is None:
        return None
    user.approval_status = REJECTED_STATUS
    user.is_active = 0
    user.approved_by = admin_id
    user.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_key: str) -> AppUser | None:
    return _find_user(db, user_key)


def reset_user_password(
    db: Session,
    user_key: str,
    new_password: str,
    *,
    must_change_password: bool = True,
) -> AppUser | None:
    user = _find_user(db, user_key)
    if user is None:
        return None
    user.password_hash = hash_password(new_password)
    user.must_change_password = 1 if must_change_password else 0
    user.failed_login_count = 0
    user.locked_until = None
    user.last_password_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user_id: str, old_password: str, new_password: str) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None or not verify_password(old_password, user.password_hash):
        raise LoginNotAllowedError("old password is incorrect")
    user.password_hash = hash_password(new_password)
    user.must_change_password = 0
    user.failed_login_count = 0
    user.locked_until = None
    user.last_password_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def create_session_for_gmail_account(
    db: Session,
    account: dict[str, Any] | GmailAccount,
    *,
    entry_scope: str | None = None,
    department_code: str | None = None,
) -> tuple[str, dict[str, Any]]:
    account_email = normalize_email(account["email"] if isinstance(account, dict) else account.email)
    account_id = str(account["id"] if isinstance(account, dict) else account.id)
    account_user_id = account.get("user_id") if isinstance(account, dict) else account.user_id
    user = db.get(AppUser, account_user_id) if account_user_id else None
    if user is None and account_email:
        user = db.scalar(select(AppUser).where(AppUser.email == account_email))
    if user is None or not _can_login(user):
        raise LoginNotAllowedError(f"{account_email or account_id} is not an approved local user")
    db_account = db.get(GmailAccount, account_id)
    if db_account is not None:
        db_account.user_id = user.id
        db_account.department_code = normalize_department_code(user.department_code, default=None)
    return create_session_for_user(
        db,
        user,
        gmail_account_id=account_id,
        entry_scope=entry_scope,
        department_code=department_code,
    )


def current_user_from_token(db: Session, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    session = db.scalar(select(AppSession).where(AppSession.token_hash == _hash_token(token)))
    if session is None or session.expires_at < datetime.utcnow():
        return None
    user = db.get(AppUser, session.user_id)
    if user is None or not _can_login(user):
        return None
    session.last_seen_at = datetime.utcnow()
    db.commit()
    return user_to_dict(
        user,
        gmail_account_id=session.gmail_account_id,
        entry_scope=session.entry_scope,
        department_code=session.department_code,
    )


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.scalar(select(AppSession).where(AppSession.token_hash == _hash_token(token)))
    if session is not None:
        db.delete(session)
        db.commit()


def _find_user(db: Session, key: str | None) -> AppUser | None:
    raw = (key or "").strip().lower()
    if not raw:
        return None
    conditions = [AppUser.id == raw, AppUser.username == raw]
    if "@" in raw:
        conditions.append(AppUser.email == raw)
    return db.scalar(select(AppUser).where(or_(*conditions)))


def _can_login(user: AppUser) -> bool:
    return bool(user.is_active) and (user.approval_status or ACTIVE_STATUS) == ACTIVE_STATUS


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
