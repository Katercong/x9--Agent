"""X9 identity assertion verification and ReplyChat principal resolution.

The Agent never accepts the original X9 session cookie and never queries an
X9 database.  X9 (or a future trusted gateway) must instead forward a
short-lived, HMAC-signed identity assertion.  The assertion is only used to
find the Agent-owned user and department memberships.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import Capability, DepartmentMembership, Principal, Role, principal_from_memberships
from .database import get_db
from .models import AuthUser, Department, UserDepartmentMembership


X9_IDENTITY_SOURCE = "x9"
X9_IDENTITY_HEADER = "X-X9-Identity"
X9_IDENTITY_SIGNATURE_HEADER = "X-X9-Identity-Signature"
X9_IDENTITY_KEY_ID_HEADER = "X-X9-Identity-Key-Id"
MAX_ASSERTION_TTL_SECONDS = 120
CLOCK_SKEW_SECONDS = 30


class IdentityConfigurationError(RuntimeError):
    """The deployment has not configured a safe identity adapter."""


class UnauthenticatedIdentityError(RuntimeError):
    """The caller did not provide a valid identity assertion."""


class ForbiddenIdentityError(RuntimeError):
    """The assertion is valid but no active local access mapping exists."""


class IdentityAdapter(Protocol):
    """Boundary for trusted identity providers; adapters never grant roles."""

    def resolve(self, request: Request, db: Session) -> Principal:
        """Resolve a request into an Agent-owned principal or fail closed."""


@dataclass(frozen=True)
class IdentitySettings:
    auth_mode: str
    app_environment: str
    issuer: str
    audience: str
    hmac_keys: Mapping[str, bytes]
    demo_identity_source: str
    demo_external_subject: str

    @classmethod
    def from_environment(cls) -> "IdentitySettings":
        raw_keys = os.getenv("X9_IDENTITY_HMAC_KEYS_JSON", "{}")
        try:
            parsed_keys = json.loads(raw_keys)
        except json.JSONDecodeError as exc:
            raise IdentityConfigurationError("X9_IDENTITY_HMAC_KEYS_JSON must be valid JSON") from exc
        if not isinstance(parsed_keys, dict) or any(
            not isinstance(key_id, str)
            or not key_id.strip()
            or not isinstance(secret, str)
            or not secret
            for key_id, secret in parsed_keys.items()
        ):
            raise IdentityConfigurationError("X9_IDENTITY_HMAC_KEYS_JSON must map non-empty key ids to secrets")

        return cls(
            auth_mode=os.getenv("RBAC_AUTH_MODE", "unconfigured").strip().lower(),
            app_environment=os.getenv("APP_ENV", "development").strip().lower(),
            issuer=os.getenv("X9_IDENTITY_ISSUER", "x9").strip(),
            audience=os.getenv("X9_IDENTITY_AUDIENCE", "x9-replychat-agent").strip(),
            hmac_keys={key_id.strip(): secret.encode("utf-8") for key_id, secret in parsed_keys.items()},
            demo_identity_source=os.getenv("RBAC_DEMO_IDENTITY_SOURCE", "demo").strip().lower(),
            demo_external_subject=os.getenv("RBAC_DEMO_EXTERNAL_SUBJECT", "demo_reviewer").strip(),
        )


def _base64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(f"{value}{'=' * (-len(value) % 4)}".encode("ascii"))
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise UnauthenticatedIdentityError("identity assertion is not valid base64url") from exc


def _required_string(claims: Mapping[str, object], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value.strip():
        raise UnauthenticatedIdentityError(f"identity assertion {name} is required")
    return value.strip()


def _timestamp(claims: Mapping[str, object], name: str) -> float:
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnauthenticatedIdentityError(f"identity assertion {name} is required")
    return float(value)


def _principal_from_local_mapping(
    db: Session,
    *,
    identity_source: str,
    external_subject: str,
) -> Principal:
    user = db.scalar(
        select(AuthUser).where(
            AuthUser.identity_source == identity_source,
            AuthUser.external_subject == external_subject,
        )
    )
    if user is None or not user.is_active:
        raise ForbiddenIdentityError("no active local user mapping")

    rows = db.execute(
        select(Department.code, UserDepartmentMembership.role)
        .join(Department, Department.id == UserDepartmentMembership.department_id)
        .where(
            UserDepartmentMembership.auth_user_id == user.id,
            UserDepartmentMembership.is_active.is_(True),
            Department.is_active.is_(True),
        )
        .order_by(Department.code.asc())
    ).all()
    if not rows:
        raise ForbiddenIdentityError("no active department membership")

    try:
        memberships = [DepartmentMembership(code, Role(role)) for code, role in rows]
    except ValueError as exc:
        raise ForbiddenIdentityError("local membership role is invalid") from exc

    return principal_from_memberships(
        user_id=user.id,
        identity_source=user.identity_source,
        external_subject=user.external_subject,
        display_name=user.display_name,
        memberships=memberships,
    )


@dataclass(frozen=True)
class X9HmacIdentityAdapter:
    issuer: str
    audience: str
    hmac_keys: Mapping[str, bytes]
    now: Callable[[], float] = time.time

    def resolve(self, request: Request, db: Session) -> Principal:
        encoded_assertion = request.headers.get(X9_IDENTITY_HEADER)
        encoded_signature = request.headers.get(X9_IDENTITY_SIGNATURE_HEADER)
        key_id = request.headers.get(X9_IDENTITY_KEY_ID_HEADER)
        if not encoded_assertion or not encoded_signature or not key_id:
            raise UnauthenticatedIdentityError("signed X9 identity assertion is required")
        secret = self.hmac_keys.get(key_id)
        if secret is None:
            raise UnauthenticatedIdentityError("identity assertion key is not accepted")

        assertion_bytes = _base64url_decode(encoded_assertion)
        supplied_signature = _base64url_decode(encoded_signature)
        expected_signature = hmac.new(secret, assertion_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise UnauthenticatedIdentityError("identity assertion signature is invalid")

        try:
            claims = json.loads(assertion_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UnauthenticatedIdentityError("identity assertion payload is invalid") from exc
        if not isinstance(claims, dict):
            raise UnauthenticatedIdentityError("identity assertion payload must be an object")

        if _required_string(claims, "issuer") != self.issuer:
            raise UnauthenticatedIdentityError("identity assertion issuer is invalid")
        if _required_string(claims, "audience") != self.audience:
            raise UnauthenticatedIdentityError("identity assertion audience is invalid")
        subject_id = _required_string(claims, "subject_id")
        _required_string(claims, "request_id")
        issued_at = _timestamp(claims, "issued_at")
        expires_at = _timestamp(claims, "expires_at")
        current_time = float(self.now())
        if (
            expires_at < issued_at
            or expires_at - issued_at > MAX_ASSERTION_TTL_SECONDS
            or issued_at > current_time + CLOCK_SKEW_SECONDS
            or expires_at < current_time - CLOCK_SKEW_SECONDS
        ):
            raise UnauthenticatedIdentityError("identity assertion is expired or outside its allowed lifetime")

        display_name = claims.get("display_name")
        if display_name is not None and not isinstance(display_name, str):
            raise UnauthenticatedIdentityError("identity assertion display_name is invalid")

        # The display name stays Agent-owned after provisioning.  The assertion
        # only proves stable external identity and must not overwrite local data.
        return _principal_from_local_mapping(
            db,
            identity_source=X9_IDENTITY_SOURCE,
            external_subject=subject_id,
        )


@dataclass(frozen=True)
class DemoIdentityAdapter:
    """Explicit local-demo identity; never permitted outside demo/test mode."""

    identity_source: str
    external_subject: str

    def resolve(self, request: Request, db: Session) -> Principal:
        return _principal_from_local_mapping(
            db,
            identity_source=self.identity_source,
            external_subject=self.external_subject,
        )


def identity_adapter_from_environment() -> IdentityAdapter:
    settings = IdentitySettings.from_environment()
    if settings.auth_mode == "x9_assertion":
        if not settings.issuer or not settings.audience or not settings.hmac_keys:
            raise IdentityConfigurationError("X9 identity assertion adapter is not fully configured")
        return X9HmacIdentityAdapter(
            issuer=settings.issuer,
            audience=settings.audience,
            hmac_keys=settings.hmac_keys,
        )
    if settings.auth_mode == "demo":
        if settings.app_environment not in {"demo", "test"}:
            raise IdentityConfigurationError("demo identity adapter is only allowed when APP_ENV is demo or test")
        if not settings.demo_identity_source or not settings.demo_external_subject:
            raise IdentityConfigurationError("demo identity adapter is not fully configured")
        return DemoIdentityAdapter(
            identity_source=settings.demo_identity_source,
            external_subject=settings.demo_external_subject,
        )
    raise IdentityConfigurationError("no supported identity adapter is configured")


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    """FastAPI dependency that turns trusted identity into local RBAC scope."""

    try:
        return identity_adapter_from_environment().resolve(request, db)
    except IdentityConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="identity provider is not configured",
        ) from exc
    except UnauthenticatedIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing identity assertion",
        ) from exc
    except ForbiddenIdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no active ReplyChat access mapping",
        ) from exc


def ensure_capability(
    principal: Principal,
    capability: Capability | str,
    *,
    department_code: str | None = None,
) -> Principal:
    """Fail closed when a principal lacks a capability in the requested scope."""

    if not principal.has_capability(capability, department_code=department_code):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient permission")
    return principal


def require_capability(capability: Capability | str):
    """Reusable route dependency for the later read/write enforcement phases."""

    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        return ensure_capability(principal, capability)

    return dependency
