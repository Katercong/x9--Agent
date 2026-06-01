from __future__ import annotations

import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


HOST_NAME = "com.companyleads.helper"
REQUIRED_HELPER_VERSION = "1.1.1"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CompanyLeads"
CONFIG_PATH = APP_DIR / "config.json"


def read_message() -> dict[str, Any]:
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return {}
    message_length = struct.unpack("<I", raw_length)[0]
    if message_length <= 0:
        return {}
    message = sys.stdin.buffer.read(message_length).decode("utf-8")
    return json.loads(message)


def write_message(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    root = Path(__file__).resolve().parents[1]
    return {
        "root": str(root),
        "backendUrl": "http://127.0.0.1:8002",
        "helperUrl": "http://127.0.0.1:8765",
    }


def http_json(url: str, timeout: float = 1.5, method: str = "GET") -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except Exception:
        return None


def api_headers(config: dict[str, Any]) -> dict[str, str]:
    token = str(config.get("apiToken") or "").strip()
    return {"X-CompanyLeads-Token": token} if token else {}


def http_json_with_headers(
    url: str,
    headers: dict[str, str],
    timeout: float = 1.5,
    method: str = "GET",
) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except Exception:
        return None


def runtime_status(root: Path) -> dict[str, Any]:
    runtime_path = root / "data" / "runtime" / "chrome-cdp.json"
    if not runtime_path.exists():
        return {}
    try:
        return json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def has_51job_cookie(runtime: dict[str, Any]) -> bool:
    user_data_dir = runtime.get("userDataDir")
    profile_directory = runtime.get("profileDirectory") or "Default"
    if not user_data_dir:
        return False

    cookie_db = Path(user_data_dir) / profile_directory / "Network" / "Cookies"
    if not cookie_db.exists():
        return False

    tmp = Path(tempfile.gettempdir()) / f"companyleads-cookie-check-{os.getpid()}.sqlite"
    try:
        shutil.copy2(cookie_db, tmp)
        with sqlite3.connect(tmp) as conn:
            row = conn.execute(
                """
                select count(*)
                from cookies
                where host_key like '%51job%'
                  and name in ('51job', 'ps', 'slife', 'guid')
                """
            ).fetchone()
        return bool(row and row[0] > 0)
    except Exception:
        return False
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


def process_env(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    python = config.get("python")
    if python:
        env["COMPANYLEADS_PYTHON"] = str(python)
    chrome_profile_dir = config.get("chromeProfileDir")
    if chrome_profile_dir:
        env["COMPANYLEADS_CHROME_USER_DATA_DIR"] = str(chrome_profile_dir)
    if config.get("mode"):
        env["COMPANYLEADS_MODE"] = str(config.get("mode"))
    if config.get("backendUrl"):
        env["COMPANYLEADS_BACKEND_URL"] = str(config.get("backendUrl")).rstrip("/")
    if config.get("backendHost"):
        env["COMPANYLEADS_BACKEND_HOST"] = str(config.get("backendHost"))
    if config.get("backendPort"):
        env["COMPANYLEADS_BACKEND_PORT"] = str(config.get("backendPort"))
    if config.get("apiToken"):
        env["COMPANYLEADS_API_TOKEN"] = str(config.get("apiToken"))
    return env


def start_stack(config: dict[str, Any]) -> None:
    root = Path(config["root"])
    script = root / "start_all.ps1"
    if not script.exists():
        raise RuntimeError(f"start_all.ps1 not found: {script}")

    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(root),
        env=process_env(config),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def wait_for_helper(helper_url: str, seconds: float = 25) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if http_json(helper_url.rstrip("/") + "/health", timeout=1):
            return True
        time.sleep(0.5)
    return False


def wait_for_cdp(root: Path, seconds: float = 25) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        runtime = runtime_status(root)
        cdp_url = runtime.get("url") or ""
        if cdp_url and http_json(str(cdp_url).rstrip("/") + "/json/version", timeout=1):
            return True
        time.sleep(0.5)
    return False


def stop_helper_port() -> None:
    if os.name != "nt":
        return
    script = (
        "$c=Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -First 1; "
        "if($c){ Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )


def ensure_started(config: dict[str, Any]) -> dict[str, Any]:
    helper_url = config.get("helperUrl", "http://127.0.0.1:8765")
    root = Path(config["root"])
    health = http_json(helper_url.rstrip("/") + "/health", timeout=1)
    if health and (not health.get("productized") or health.get("version") != REQUIRED_HELPER_VERSION):
        stop_helper_port()
        health = None
        time.sleep(0.5)
    if not health:
        start_stack(config)
        wait_for_helper(helper_url)
    if not wait_for_cdp(root, seconds=2):
        start_stack(config)
        wait_for_helper(helper_url)
        wait_for_cdp(root, seconds=15)
    return get_status(config)


def open_url_in_cdp(cdp_url: str, url: str) -> bool:
    encoded = urllib.parse.quote(url, safe="")
    endpoint = cdp_url.rstrip("/") + "/json/new?" + encoded
    return http_json(endpoint, timeout=2, method="PUT") is not None


def get_status(config: dict[str, Any]) -> dict[str, Any]:
    root = Path(config["root"])
    helper_url = config.get("helperUrl", "http://127.0.0.1:8765")
    backend_url = config.get("backendUrl", "http://127.0.0.1:8002")
    helper_health = http_json(helper_url.rstrip("/") + "/health", timeout=1)
    headers = api_headers(config)
    backend_health = http_json_with_headers(backend_url.rstrip("/") + "/api/stats", headers, timeout=1)
    system_status = http_json_with_headers(backend_url.rstrip("/") + "/api/system/status", headers, timeout=1)
    runtime = runtime_status(root)
    cdp_url = runtime.get("url") or ""
    cdp_ready = bool(cdp_url and http_json(str(cdp_url).rstrip("/") + "/json/version", timeout=1))
    helper_ready = helper_health is not None
    backend_ready = backend_health is not None

    if helper_ready and backend_ready and cdp_ready:
        status = "ready"
    elif helper_ready:
        status = "helper_connected"
    else:
        status = "not_running"

    return {
        "ok": helper_ready,
        "host": HOST_NAME,
        "status": status,
        "helperReady": helper_ready,
        "backendReady": backend_ready,
        "cdpReady": cdp_ready,
        "helperUrl": helper_url,
        "backendUrl": backend_url,
        "mode": config.get("mode", "server"),
        "apiTokenConfigured": bool(config.get("apiToken")),
        "systemStatus": system_status,
        "cdpUrl": cdp_url,
        "runtime": runtime,
        "helperHealth": helper_health,
    }


def open_chrome(config: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    status = ensure_started(config)
    payload = payload or {}
    url = payload.get("url")
    if not url:
        # Prefer the work site. If the controlled profile is not logged in,
        # 51job will redirect to its login flow by itself.
        url = "https://we.51job.com/"
    cdp_url = status.get("cdpUrl")
    opened = bool(cdp_url and open_url_in_cdp(str(cdp_url), str(url)))
    if not opened:
        start_stack(config)
        wait_for_cdp(Path(config["root"]), seconds=15)
        status = get_status(config)
        cdp_url = status.get("cdpUrl")
        opened = bool(cdp_url and open_url_in_cdp(str(cdp_url), str(url)))
    if not opened:
        raise RuntimeError("Chrome CDP is not ready; could not open controlled Chrome tab.")
    status["opened"] = url
    return status


def open_dashboard(config: dict[str, Any]) -> dict[str, Any]:
    status = ensure_started(config)
    backend_url = status.get("backendUrl") or config.get("backendUrl", "http://127.0.0.1:8002")
    if os.name == "nt":
        os.startfile(str(backend_url))  # type: ignore[attr-defined]
    return status


def handle(request: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    message_type = request.get("type")
    payload = request.get("payload") or {}

    if message_type == "helper.ensureStarted":
        return ensure_started(config)
    if message_type == "helper.getStatus":
        return get_status(config)
    if message_type == "helper.openChrome":
        return open_chrome(config, payload)
    if message_type == "helper.openDashboard":
        return open_dashboard(config)
    if message_type == "helper.getConfig":
        safe = dict(config)
        if safe.get("apiToken"):
            safe["apiToken"] = "***"
        return {"ok": True, "host": HOST_NAME, "config": safe}
    if message_type == "helper.getClientConfig":
        return {
            "ok": True,
            "host": HOST_NAME,
            "config": {
                "backendUrl": str(config.get("backendUrl", "http://127.0.0.1:8002")).rstrip("/"),
                "apiToken": str(config.get("apiToken") or ""),
                "mode": config.get("mode", "server"),
            },
        }

    return {"ok": False, "host": HOST_NAME, "error": f"Unknown message type: {message_type}"}


def main() -> None:
    try:
        request = read_message()
        response = handle(request)
        response.setdefault("ok", True)
    except Exception as exc:
        response = {"ok": False, "host": HOST_NAME, "error": str(exc)}
    write_message(response)


if __name__ == "__main__":
    main()
