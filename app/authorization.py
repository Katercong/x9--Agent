"""与 Web 框架和外部身份源解耦的 ReplyChat 授权策略。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .department_codes_current import validate_department_code


class Role(str, Enum):
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class Capability(str, Enum):
    CATALOG_READ = "catalog:read"
    REVIEW_READ = "review:read"
    DRAFT_EXPORT = "draft:export"
    REVIEW_DECIDE = "review:decide"
    RUN_ENQUEUE = "run:enqueue"
    RUN_RETRY = "run:retry"
    DNC_DECIDE = "dnc:decide"
    DELIVERY_CONFIRM = "delivery:confirm"
    CREATOR_MANAGE = "creator:manage"
    CATALOG_MANAGE = "catalog:manage"
    SIMULATION_WRITE = "simulation:write"
    OUTBOUND_READ = "outbound:read"
    ACCESS_MANAGE = "access:manage"


_OPERATOR_CAPABILITIES = frozenset(
    {
        Capability.CATALOG_READ,
        Capability.REVIEW_READ,
        Capability.DRAFT_EXPORT,
    }
)
_REVIEWER_CAPABILITIES = _OPERATOR_CAPABILITIES | frozenset(
    {
        Capability.REVIEW_DECIDE,
        Capability.RUN_ENQUEUE,
        Capability.RUN_RETRY,
        Capability.DNC_DECIDE,
        Capability.DELIVERY_CONFIRM,
    }
)
_ADMIN_CAPABILITIES = _REVIEWER_CAPABILITIES | frozenset(
    {
        Capability.CREATOR_MANAGE,
        Capability.CATALOG_MANAGE,
        Capability.SIMULATION_WRITE,
        Capability.OUTBOUND_READ,
        Capability.ACCESS_MANAGE,
    }
)

ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.OPERATOR: _OPERATOR_CAPABILITIES,
    Role.REVIEWER: _REVIEWER_CAPABILITIES,
    Role.ADMIN: _ADMIN_CAPABILITIES,
}


def normalise_role(value: Role | str) -> Role:
    """将持久化角色值转换为受限枚举，拒绝未知角色。"""

    return value if isinstance(value, Role) else Role(value)


@dataclass(frozen=True)
class DepartmentMembership:
    department_code: str
    role: Role

    def __post_init__(self) -> None:
        code = validate_department_code(self.department_code)
        object.__setattr__(self, "department_code", code)
        object.__setattr__(self, "role", normalise_role(self.role))


@dataclass(frozen=True)
class Principal:
    """认证完成后的不可变主体；后续 Adapter 只负责构造它。"""

    user_id: str
    identity_source: str
    external_subject: str
    display_name: str | None
    memberships: tuple[DepartmentMembership, ...]

    def __post_init__(self) -> None:
        if not self.user_id.strip() or not self.identity_source.strip() or not self.external_subject.strip():
            raise ValueError("principal identity fields must not be empty")
        codes = [membership.department_code for membership in self.memberships]
        if len(codes) != len(set(codes)):
            raise ValueError("principal memberships must not repeat a department")

    @property
    def department_codes(self) -> frozenset[str]:
        return frozenset(membership.department_code for membership in self.memberships)

    def membership_for(self, department_code: str) -> DepartmentMembership | None:
        wanted = validate_department_code(department_code)
        return next((membership for membership in self.memberships if membership.department_code == wanted), None)

    def can_access_department(self, department_code: str) -> bool:
        return self.membership_for(department_code) is not None

    def allowed_departments_for(self, capability: Capability | str) -> frozenset[str]:
        required = Capability(capability)
        return frozenset(
            membership.department_code
            for membership in self.memberships
            if required in ROLE_CAPABILITIES[membership.role]
        )

    def has_capability(self, capability: Capability | str, *, department_code: str | None = None) -> bool:
        required = Capability(capability)
        if department_code is None:
            return bool(self.allowed_departments_for(required))
        membership = self.membership_for(department_code)
        return membership is not None and required in ROLE_CAPABILITIES[membership.role]


def principal_from_memberships(
    *,
    user_id: str,
    identity_source: str,
    external_subject: str,
    display_name: str | None,
    memberships: Iterable[DepartmentMembership],
) -> Principal:
    """让 ORM Adapter 可在下一阶段安全地构造统一 Principal。"""

    return Principal(
        user_id=user_id,
        identity_source=identity_source,
        external_subject=external_subject,
        display_name=display_name,
        memberships=tuple(memberships),
    )
