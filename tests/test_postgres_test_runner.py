"""Safety checks for the local PowerShell PostgreSQL test entry point."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "run-postgres-tests.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def _write_command_stubs(command_bin: Path, *, docker_exit_code: int, python_exit_code: int) -> None:
    if os.name == "nt":
        (command_bin / "docker.cmd").write_text(
            "@echo off\n"
            "echo docker %*>> \"%X9_POSTGRES_RUNNER_LOG%\"\n"
            f"exit /b {docker_exit_code}\n",
            encoding="utf-8",
        )
        (command_bin / "python.cmd").write_text(
            "@echo off\n"
            "echo python %* %POSTGRES_TEST_ADMIN_URL%>> \"%X9_POSTGRES_RUNNER_LOG%\"\n"
            f"exit /b {python_exit_code}\n",
            encoding="utf-8",
        )
        return

    (command_bin / "docker").write_text(
        "#!/bin/sh\n"
        "printf 'docker %s\\n' \"$*\" >> \"$X9_POSTGRES_RUNNER_LOG\"\n"
        f"exit {docker_exit_code}\n",
        encoding="utf-8",
    )
    (command_bin / "python").write_text(
        "#!/bin/sh\n"
        "printf 'python %s %s\\n' \"$*\" \"$POSTGRES_TEST_ADMIN_URL\" >> \"$X9_POSTGRES_RUNNER_LOG\"\n"
        f"exit {python_exit_code}\n",
        encoding="utf-8",
    )
    for command in command_bin.iterdir():
        command.chmod(0o755)


def _run_runner(tmp_path: Path, *, docker_exit_code: int, include_port: bool) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    command_log = tmp_path / "commands.log"
    command_bin = tmp_path / "commands"
    command_bin.mkdir()
    _write_command_stubs(command_bin, docker_exit_code=docker_exit_code, python_exit_code=0)

    environment = os.environ.copy()
    environment["PATH"] = f"{command_bin}{os.pathsep}{environment['PATH']}"
    environment["X9_POSTGRES_RUNNER_LOG"] = str(command_log)
    command = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER_SCRIPT)]
    if include_port:
        command.extend(["-Port", "55433"])

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, command_log.read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required to exercise the local test runner")
def test_postgres_test_runner_stops_before_connecting_when_compose_startup_fails(tmp_path: Path):
    """A failed Docker bootstrap must not target a process already bound to the port."""

    result, commands = _run_runner(tmp_path, docker_exit_code=41, include_port=True)

    assert result.returncode != 0
    assert "Dedicated PostgreSQL test Compose startup failed" in result.stderr
    assert len(commands) == 1
    assert commands[0].startswith("docker compose")
    assert " up " in f" {commands[0]} "
    assert "python" not in commands[0]
    assert " down " not in f" {commands[0]} "


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required to exercise the local test runner")
def test_postgres_test_runner_uses_a_process_scoped_project_and_dynamic_port(tmp_path: Path):
    """Parallel local runs must not share Compose resources or the fixed default port."""

    result, commands = _run_runner(tmp_path, docker_exit_code=0, include_port=False)

    assert result.returncode == 0, result.stderr
    assert len(commands) == 3
    assert commands[0].startswith("docker compose")
    assert commands[1].startswith("python scripts/run_postgres_tests.py")
    assert commands[2].startswith("docker compose")
    assert " up " in f" {commands[0]} "
    assert " down " in f" {commands[2]} "

    project_names = re.findall(r"--project-name (x9-replychat-test-\d+)", "\n".join(commands))
    assert len(project_names) == 2
    assert project_names[0] == project_names[1]
    assert re.search(r"@127\.0\.0\.1:\d+/postgres$", commands[1])
