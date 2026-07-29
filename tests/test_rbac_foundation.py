from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False, suffix='.db').name}"

import pytest
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.authorization import Capability, DepartmentMembership, Principal, Role, principal_from_memberships
from app.database import Base, SessionLocal, engine
from app.models import AuthUser, AuthorizationAuditEvent, Department, UserDepartmentMembership
from app.rbac_bootstrap import bootstrap_admin, main as bootstrap_main


@pytest.fixture(autouse=True)
def reset_rbac_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _principal(role: Role) -> Principal:
    return principal_from_memberships(
        user_id="auth_user_test",
        identity_source="x9",
        external_subject="x9-subject-test",
        display_name="Test User",
        memberships=[DepartmentMembership("cross_border", role)],
    )


def test_role_capability_matrix_and_department_scope_are_explicit():
    operator = _principal(Role.OPERATOR)
    reviewer = _principal(Role.REVIEWER)
    admin = _principal(Role.ADMIN)

    assert operator.has_capability(Capability.REVIEW_READ, department_code="cross_border")
    assert operator.has_capability(Capability.DRAFT_EXPORT, department_code="cross_border")
    assert not operator.has_capability(Capability.REVIEW_DECIDE, department_code="cross_border")
    assert not operator.has_capability(Capability.DRAFT_EXPORT, department_code="foreign_trade")

    assert reviewer.has_capability(Capability.REVIEW_DECIDE, department_code="cross_border")
    assert reviewer.has_capability(Capability.DNC_DECIDE, department_code="cross_border")
    assert not reviewer.has_capability(Capability.ACCESS_MANAGE, department_code="cross_border")

    assert admin.has_capability(Capability.ACCESS_MANAGE, department_code="cross_border")
    assert admin.has_capability(Capability.CATALOG_MANAGE, department_code="cross_border")
    assert admin.allowed_departments_for(Capability.REVIEW_READ) == {"cross_border"}


def test_principal_rejects_empty_or_duplicate_department_memberships():
    with pytest.raises(ValueError, match="must not be empty"):
        DepartmentMembership("  ", Role.OPERATOR)

    with pytest.raises(ValueError, match="must not repeat"):
        principal_from_memberships(
            user_id="user",
            identity_source="x9",
            external_subject="subject",
            display_name=None,
            memberships=[
                DepartmentMembership("cross_border", Role.OPERATOR),
                DepartmentMembership("cross_border", Role.REVIEWER),
            ],
        )


def test_authorization_models_enforce_unique_roles_and_restrict_deletes():
    with SessionLocal() as db:
        user = AuthUser(id="auth_user_unique", identity_source="x9", external_subject="subject_unique")
        department = Department(id="department_unique", code="department_unique", name="Unique Department")
        db.add_all([user, department])
        db.commit()

        db.add(AuthUser(id="auth_user_duplicate", identity_source="x9", external_subject="subject_unique"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        membership = UserDepartmentMembership(
            id="membership_unique",
            auth_user_id=user.id,
            department_id=department.id,
            role=Role.REVIEWER.value,
        )
        db.add(membership)
        db.commit()

        db.add(
            UserDepartmentMembership(
                id="membership_duplicate",
                auth_user_id=user.id,
                department_id=department.id,
                role=Role.OPERATOR.value,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            UserDepartmentMembership(
                id="membership_invalid_role",
                auth_user_id=user.id,
                department_id=department.id,
                role="unknown",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            AuthorizationAuditEvent(
                id="authorization_audit_unique",
                action="test_membership",
                target_auth_user_id=user.id,
                department_id=department.id,
            )
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(delete(AuthUser).where(AuthUser.id == user.id))
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(delete(Department).where(Department.id == department.id))
            db.commit()
        db.rollback()


def test_authorization_tables_compile_for_sqlite_and_postgresql_with_restrict_foreign_keys():
    tables = (AuthUser.__table__, Department.__table__, UserDepartmentMembership.__table__, AuthorizationAuditEvent.__table__)
    for table in tables:
        sqlite_sql = str(CreateTable(table).compile(dialect=sqlite.dialect()))
        postgresql_sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in sqlite_sql
        assert "CREATE TABLE" in postgresql_sql

    membership_postgresql_sql = str(CreateTable(UserDepartmentMembership.__table__).compile(dialect=postgresql.dialect()))
    audit_postgresql_sql = str(CreateTable(AuthorizationAuditEvent.__table__).compile(dialect=postgresql.dialect()))
    assert membership_postgresql_sql.count("ON DELETE RESTRICT") == 3
    assert audit_postgresql_sql.count("ON DELETE RESTRICT") == 3


def test_bootstrap_admin_is_explicit_idempotent_and_audited(capsys):
    with SessionLocal() as db:
        first = bootstrap_admin(
            db,
            identity_source="x9",
            external_subject="x9-first-admin",
            department_code="cross_border",
            department_name="Cross Border",
            display_name="First Admin",
        )
        db.commit()
        second = bootstrap_admin(
            db,
            identity_source="x9",
            external_subject="x9-first-admin",
            department_code="cross_border",
            department_name="Cross Border",
            display_name="First Admin",
        )
        db.commit()

        assert first[3] is True
        assert second[3] is False
        assert db.scalar(select(AuthUser).where(AuthUser.external_subject == "x9-first-admin")).is_active is True
        membership = db.scalar(select(UserDepartmentMembership).where(UserDepartmentMembership.id == first[2].id))
        assert membership is not None
        assert membership.role == Role.ADMIN.value
        assert db.scalar(select(AuthorizationAuditEvent).where(AuthorizationAuditEvent.action == "bootstrap_admin_membership"))
        assert len(db.scalars(select(AuthorizationAuditEvent)).all()) == 1

    with pytest.raises(SystemExit, match="--confirm"):
        bootstrap_main(
            [
                "--identity-source",
                "x9",
                "--external-subject",
                "x9-no-confirm",
                "--department-code",
                "cross_border",
            ]
        )

    assert bootstrap_main(
        [
            "--identity-source",
            "x9",
            "--external-subject",
            "x9-cli-admin",
            "--department-code",
            "foreign_trade",
            "--confirm",
        ]
    ) == 0
    assert '"department_code": "foreign_trade"' in capsys.readouterr().out


def test_rbac_foundation_migration_upgrades_and_downgrades_sqlite(tmp_path: Path):
    db_path = tmp_path / "rbac_migration.sqlite"
    database_url = f"sqlite:///{db_path.as_posix()}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    def run_alembic(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    run_alembic("upgrade", "c4d5e6f7a8b9")
    run_alembic("upgrade", "head")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"auth_users", "departments", "user_department_memberships", "authorization_audit_events"} <= tables
        foreign_keys = connection.execute("PRAGMA foreign_key_list(user_department_memberships)").fetchall()
        assert {row[6] for row in foreign_keys} == {"RESTRICT"}

    run_alembic("downgrade", "c4d5e6f7a8b9")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "auth_users" not in tables
        assert "authorization_audit_events" not in tables
