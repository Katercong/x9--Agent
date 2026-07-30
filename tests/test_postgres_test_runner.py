"""Safety checks for the local PowerShell PostgreSQL test entry point."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "run-postgres-tests.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required to exercise the local test runner")
def test_postgres_test_runner_stops_before_connecting_when_compose_startup_fails(tmp_path: Path):
    """A failed Docker bootstrap must not target a process already bound to the port."""

    command_log = tmp_path / "commands.log"
    command_bin = tmp_path / "commands"
    command_bin.mkdir()

    if os.name == "nt":
        (command_bin / "docker.cmd").write_text(
            "@echo off\n"
            "echo docker %*>> \"%X9_POSTGRES_RUNNER_LOG%\"\n"
            "exit /b 41\n",
            encoding="utf-8",
        )
        (command_bin / "python.cmd").write_text(
            "@echo off\n"
            "echo python %*>> \"%X9_POSTGRES_RUNNER_LOG%\"\n"
            "exit /b 0\n",
            encoding="utf-8",
        )
    else:
        (command_bin / "docker").write_text(
            "#!/bin/sh\n"
            "printf 'docker %s\\n' \"$*\" >> \"$X9_POSTGRES_RUNNER_LOG\"\n"
            "exit 41\n",
            encoding="utf-8",
        )
        (command_bin / "python").write_text(
            "#!/bin/sh\n"
            "printf 'python %s\\n' \"$*\" >> \"$X9_POSTGRES_RUNNER_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        for command in command_bin.iterdir():
            command.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{command_bin}{os.pathsep}{environment['PATH']}"
    environment["X9_POSTGRES_RUNNER_LOG"] = str(command_log)

    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER_SCRIPT), "-Port", "55433"],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Dedicated PostgreSQL test Compose startup failed" in result.stderr
    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert len(commands) == 1
    assert commands[0].startswith("docker compose")
    assert " up " in f" {commands[0]} "
    assert "python" not in commands[0]
    assert " down " not in f" {commands[0]} "
