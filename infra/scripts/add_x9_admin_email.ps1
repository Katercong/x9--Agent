param(
  [string]$Email = "",
  [string]$Role = "admin"
)

$ErrorActionPreference = "Stop"

$StartDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Email) {
  $Email = Read-Host "Gmail email to allow"
}
if (-not $Email -or $Email -notmatch "@") {
  throw "A valid Gmail email is required."
}
if ($Role -notin @("admin", "bd", "viewer")) {
  throw "Role must be admin, bd, or viewer."
}

$env:X9_USER_EMAIL = $Email
$env:X9_USER_ROLE = $Role

Push-Location $StartDir
try {
  @'
import os

from x9_creator_desktop_system.backend.database import SessionLocal, init_db
from x9_creator_desktop_system.backend.services.auth_service import upsert_user

email = os.environ["X9_USER_EMAIL"]
role = os.environ.get("X9_USER_ROLE", "admin")

init_db()
with SessionLocal() as db:
    user = upsert_user(
        db,
        email=email,
        role=role,
        is_active=True,
        created_by="local-admin-script",
    )
    print(f"Allowed {user.email} as {user.role}")
'@ | py -3.11 -
} finally {
  Pop-Location
}
