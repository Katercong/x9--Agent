from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import auth_service


router = APIRouter(prefix="/api/local/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None
    department_code: str = "cross_border"


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class UserIn(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None
    role: str = "department_user"
    department_code: str | None = "cross_border"
    display_name: str | None = None
    is_active: bool = True
    approval_status: str | None = "active"


class UserPatch(BaseModel):
    role: str | None = None
    department_code: str | None = None
    display_name: str | None = None
    is_active: bool | None = None
    approval_status: str | None = None


class ResetPasswordIn(BaseModel):
    new_password: str
    must_change_password: bool = True


def _current_user(request: Request) -> dict | None:
    return getattr(request.state, "current_user", None)


def require_admin(request: Request) -> dict:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    if user.get("role") not in auth_service.ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="admin only")
    return user


def require_user_manager(request: Request) -> dict:
    user = require_admin(request)
    if not auth_service.actor_can_manage_users(user):
        raise HTTPException(status_code=403, detail="company admin only")
    return user


def require_super_admin(request: Request) -> dict:
    user = require_admin(request)
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="super admin only")
    return user


@router.get("/me")
def me(request: Request) -> dict:
    user = _current_user(request)
    if not user:
        return {"ok": True, "logged_in": False}
    return {"ok": True, "logged_in": True, "user": user}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    try:
        user = auth_service.register_user(
            db,
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
            department_code=body.department_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "status": user.approval_status, "user": auth_service.user_to_dict(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> JSONResponse:
    try:
        token, user = auth_service.authenticate_user(db, body.username, body.password)
    except auth_service.LoginNotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    response = JSONResponse({"ok": True, "user": user})
    response.set_cookie(
        auth_service.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=auth_service.SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    auth_service.revoke_session(db, request.cookies.get(auth_service.SESSION_COOKIE))
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/")
    return response


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    try:
        row = auth_service.change_password(db, user["id"], body.old_password, body.new_password)
    except (ValueError, auth_service.LoginNotAllowedError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "user": auth_service.user_to_dict(row)}


@router.get("/users")
def users(admin: dict = Depends(require_user_manager), db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "items": auth_service.list_users(db, actor=admin)}


@router.post("/users")
def add_user(body: UserIn, admin: dict = Depends(require_user_manager), db: Session = Depends(get_db)) -> dict:
    role = auth_service.normalize_role(body.role)
    if not auth_service.actor_can_manage_role(admin, role):
        raise HTTPException(status_code=403, detail="insufficient role management permission")
    try:
        user = auth_service.upsert_user(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
            role=role,
            department_code=body.department_code,
            display_name=body.display_name,
            is_active=body.is_active,
            approval_status=body.approval_status,
            created_by=admin.get("id") or admin.get("identity"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "user": auth_service.user_to_dict(user)}


@router.patch("/users/{user_key}")
def update_user(
    user_key: str,
    body: UserPatch,
    admin: dict = Depends(require_user_manager),
    db: Session = Depends(get_db),
) -> dict:
    role = auth_service.normalize_role(body.role) if body.role is not None else None
    existing = auth_service.get_user(db, user_key)
    if existing is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not auth_service.actor_can_manage_role(admin, role or existing.role):
        raise HTTPException(status_code=403, detail="insufficient role management permission")
    user = auth_service.patch_user(
        db,
        user_key,
        role=role,
        department_code=body.department_code,
        display_name=body.display_name,
        is_active=body.is_active,
        approval_status=body.approval_status,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True, "user": auth_service.user_to_dict(user)}


@router.post("/users/{user_key}/approve")
def approve_user(
    user_key: str,
    admin: dict = Depends(require_user_manager),
    db: Session = Depends(get_db),
) -> dict:
    existing = auth_service.get_user(db, user_key)
    if existing is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not auth_service.actor_can_manage_role(admin, existing.role):
        raise HTTPException(status_code=403, detail="insufficient role management permission")
    user = auth_service.approve_user(db, user_key, admin.get("id"))
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True, "user": auth_service.user_to_dict(user)}


@router.post("/users/{user_key}/reject")
def reject_user(
    user_key: str,
    admin: dict = Depends(require_user_manager),
    db: Session = Depends(get_db),
) -> dict:
    existing = auth_service.get_user(db, user_key)
    if existing is None:
        raise HTTPException(status_code=404, detail="user not found")
    if not auth_service.actor_can_manage_role(admin, existing.role):
        raise HTTPException(status_code=403, detail="insufficient role management permission")
    user = auth_service.reject_user(db, user_key, admin.get("id"))
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True, "user": auth_service.user_to_dict(user)}


@router.post("/users/{user_key}/reset-password")
def reset_password(
    user_key: str,
    body: ResetPasswordIn,
    _admin: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        user = auth_service.reset_user_password(
            db,
            user_key,
            body.new_password,
            must_change_password=body.must_change_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True, "user": auth_service.user_to_dict(user)}
