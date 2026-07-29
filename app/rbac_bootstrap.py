"""显式建立首个 ReplyChat 管理员；应用启动路径绝不自动调用。"""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import Role
from .database import SessionLocal
from .models import AuthUser, AuthorizationAuditEvent, Department, UserDepartmentMembership
from .services import new_id


def _membership_snapshot(membership: UserDepartmentMembership | None) -> dict[str, object] | None:
    if membership is None:
        return None
    return {
        "role": membership.role,
        "is_active": bool(membership.is_active),
        "authorization_source": membership.authorization_source,
    }


def bootstrap_admin(
    db: Session,
    *,
    identity_source: str,
    external_subject: str,
    department_code: str,
    department_name: str | None = None,
    display_name: str | None = None,
) -> tuple[AuthUser, Department, UserDepartmentMembership, bool]:
    """幂等创建首个管理员及其部门成员关系，并记录一次 bootstrap 审计。"""

    source = identity_source.strip().lower()
    subject = external_subject.strip()
    code = department_code.strip().lower()
    if not source or not subject or not code:
        raise ValueError("identity source, external subject and department code are required")

    user = db.scalar(
        select(AuthUser).where(
            AuthUser.identity_source == source,
            AuthUser.external_subject == subject,
        )
    )
    changed = False
    if user is None:
        user = AuthUser(
            id=new_id("auth_user"),
            identity_source=source,
            external_subject=subject,
            display_name=display_name.strip() if display_name and display_name.strip() else None,
            is_active=True,
        )
        db.add(user)
        changed = True
    elif not user.is_active:
        user.is_active = True
        changed = True
    elif display_name and display_name.strip() and user.display_name != display_name.strip():
        user.display_name = display_name.strip()
        changed = True

    department = db.scalar(select(Department).where(Department.code == code))
    desired_department_name = department_name.strip() if department_name and department_name.strip() else code
    if department is None:
        department = Department(id=new_id("department"), code=code, name=desired_department_name, is_active=True)
        db.add(department)
        changed = True
    elif not department.is_active:
        department.is_active = True
        changed = True

    db.flush()
    membership = db.scalar(
        select(UserDepartmentMembership).where(
            UserDepartmentMembership.auth_user_id == user.id,
            UserDepartmentMembership.department_id == department.id,
        )
    )
    before = _membership_snapshot(membership)
    if membership is None:
        membership = UserDepartmentMembership(
            id=new_id("membership"),
            auth_user_id=user.id,
            department_id=department.id,
            role=Role.ADMIN.value,
            is_active=True,
            authorization_source="bootstrap",
        )
        db.add(membership)
        changed = True
    else:
        if membership.role != Role.ADMIN.value:
            membership.role = Role.ADMIN.value
            changed = True
        if not membership.is_active:
            membership.is_active = True
            changed = True
        if membership.authorization_source != "bootstrap":
            membership.authorization_source = "bootstrap"
            changed = True

    if changed:
        db.add(
            AuthorizationAuditEvent(
                id=new_id("auth_audit"),
                action="bootstrap_admin_membership",
                actor_auth_user_id=None,
                target_auth_user_id=user.id,
                department_id=department.id,
                before_json=json.dumps(before, sort_keys=True) if before is not None else None,
                after_json=json.dumps(
                    {
                        "role": Role.ADMIN.value,
                        "is_active": True,
                        "authorization_source": "bootstrap",
                    },
                    sort_keys=True,
                ),
            )
        )
    return user, department, membership, changed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or reactivate the first ReplyChat department admin.")
    parser.add_argument("--identity-source", required=True)
    parser.add_argument("--external-subject", required=True)
    parser.add_argument("--department-code", required=True)
    parser.add_argument("--department-name")
    parser.add_argument("--display-name")
    parser.add_argument("--confirm", action="store_true", help="required acknowledgement for this privileged write")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.confirm:
        raise SystemExit("refusing privileged write without --confirm")
    with SessionLocal() as db:
        user, department, membership, changed = bootstrap_admin(
            db,
            identity_source=args.identity_source,
            external_subject=args.external_subject,
            department_code=args.department_code,
            department_name=args.department_name,
            display_name=args.display_name,
        )
        db.commit()
        result = {
            "changed": changed,
            "auth_user_id": user.id,
            "department_code": department.code,
            "membership_id": membership.id,
            "role": membership.role,
        }
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main().
    raise SystemExit(main())
