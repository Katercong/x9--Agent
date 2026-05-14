from __future__ import annotations

import csv
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SCRIPT_PATH = BASE_DIR / "youtube_email_grabber.py"
MAX_PREVIEW_ROWS = 300
DEFAULT_PORT = 8765


@dataclass
class JobState:
    running: bool = False
    status: str = "idle"
    started_at: str = ""
    finished_at: str = ""
    command: list[str] = field(default_factory=list)
    output_path: str = ""
    verification_output_path: str = ""
    logs: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    verification_rows: list[dict[str, str]] = field(default_factory=list)
    row_count: int = 0
    verification_count: int = 0
    exit_code: int | None = None
    error: str = ""
    process: subprocess.Popen | None = None


app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
state = JobState()
state_lock = threading.Lock()


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_output_path(filename: str) -> Path:
    value = (filename or "").strip()
    if not value:
        value = f"youtube_emails_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    if not value.lower().endswith(".csv"):
        value = f"{value}.csv"

    path = Path(value)
    if not path.is_absolute():
        path = OUTPUT_DIR / path.name

    resolved = path.resolve()
    output_root = OUTPUT_DIR.resolve()
    if not str(resolved).lower().startswith(str(output_root).lower()):
        resolved = output_root / resolved.name

    return resolved


def read_preview_rows(path: Path) -> tuple[list[dict[str, str]], int]:
    if not path.exists():
        return [], 0

    rows: list[dict[str, str]] = []
    total = 0
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total += 1
            if len(rows) < MAX_PREVIEW_ROWS:
                rows.append({key: value for key, value in row.items()})

    return rows, total


def default_verification_queue_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_verification_queue.csv")


def build_command(payload: dict[str, Any]) -> tuple[list[str], Path, Path]:
    queries_text = str(payload.get("queries", "")).strip()
    queries = [line.strip() for line in queries_text.splitlines() if line.strip()]
    if not queries:
        raise ValueError("请至少输入一个关键词。")

    max_results = int(payload.get("max_results") or 25)
    if max_results < 1 or max_results > 200:
        raise ValueError("每个关键词的视频数建议设置在 1 到 200 之间。")

    order = str(payload.get("order") or "relevance")
    if order not in {"relevance", "date"}:
        raise ValueError("排序只能选择 relevance 或 date。")

    published_after = str(payload.get("published_after") or "").strip()
    sleep_seconds = float(payload.get("sleep") or 0)
    keep_duplicates = bool(payload.get("keep_duplicates"))
    scan_about = bool(payload.get("scan_about", True))
    yt_dlp_path = str(payload.get("yt_dlp_path") or "").strip()
    output_path = safe_output_path(str(payload.get("output_filename") or ""))
    verification_output_path = default_verification_queue_path(output_path)

    command = [
        sys.executable,
        "-B",
        "-u",
        str(SCRIPT_PATH),
        "--max-results",
        str(max_results),
        "--order",
        order,
        "--output",
        str(output_path),
        "--verification-queue-output",
        str(verification_output_path),
        "--sleep",
        str(sleep_seconds),
    ]

    for query in queries:
        command.extend(["--query", query])

    if published_after:
        command.extend(["--published-after", published_after])
    if keep_duplicates:
        command.append("--keep-duplicates")
    if not scan_about:
        command.append("--skip-channel-about")
    if yt_dlp_path:
        command.extend(["--yt-dlp-path", yt_dlp_path])

    return command, output_path, verification_output_path


def append_log(line: str) -> None:
    with state_lock:
        state.logs.append(line.rstrip())
        if len(state.logs) > 1000:
            state.logs = state.logs[-1000:]


def run_job(command: list[str], output_path: Path, verification_output_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process: subprocess.Popen | None = None

    try:
        process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        with state_lock:
            state.process = process

        assert process.stdout is not None
        for line in process.stdout:
            append_log(line)

        exit_code = process.wait()
        rows, row_count = read_preview_rows(output_path)
        verification_rows, verification_count = read_preview_rows(verification_output_path)
        with state_lock:
            state.running = False
            state.status = "completed" if exit_code == 0 else "failed"
            state.finished_at = now_label()
            state.exit_code = exit_code
            state.rows = rows
            state.verification_rows = verification_rows
            state.row_count = row_count
            state.verification_count = verification_count
            state.error = "" if exit_code == 0 else f"抓取进程退出码：{exit_code}"
            state.process = None
    except Exception as exc:
        with state_lock:
            state.running = False
            state.status = "failed"
            state.finished_at = now_label()
            state.exit_code = None
            state.error = str(exc)
            state.process = None


def serialize_state() -> dict[str, Any]:
    with state_lock:
        has_output = bool(state.output_path and Path(state.output_path).exists())
        has_verification_output = bool(state.verification_output_path and Path(state.verification_output_path).exists())
        return {
            "running": state.running,
            "status": state.status,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "command": " ".join(state.command),
            "output_path": state.output_path,
            "verification_output_path": state.verification_output_path,
            "has_output": has_output,
            "has_verification_output": has_verification_output,
            "logs": list(state.logs),
            "rows": list(state.rows),
            "verification_rows": list(state.verification_rows),
            "row_count": state.row_count,
            "verification_count": state.verification_count,
            "exit_code": state.exit_code,
            "error": state.error,
        }


@app.get("/")
def index() -> str:
    default_queries = ""
    example_file = BASE_DIR / "queries.txt.example"
    if example_file.exists():
        default_queries = example_file.read_text(encoding="utf-8").strip()
    return render_template("index.html", default_queries=default_queries)


@app.post("/api/start")
def start_job():
    payload = request.get_json(silent=True) or {}

    with state_lock:
        if state.running:
            return jsonify({"ok": False, "error": "当前已有任务正在运行。"}), 409

    try:
        command, output_path, verification_output_path = build_command(payload)
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with state_lock:
        state.running = True
        state.status = "running"
        state.started_at = now_label()
        state.finished_at = ""
        state.command = command
        state.output_path = str(output_path)
        state.verification_output_path = str(verification_output_path)
        state.logs = ["任务已启动。"]
        state.rows = []
        state.verification_rows = []
        state.row_count = 0
        state.verification_count = 0
        state.exit_code = None
        state.error = ""
        state.process = None

    thread = threading.Thread(target=run_job, args=(command, output_path, verification_output_path), daemon=True)
    thread.start()
    return jsonify({"ok": True, "state": serialize_state()})


@app.post("/api/stop")
def stop_job():
    with state_lock:
        process = state.process
        if not state.running:
            return jsonify({"ok": True, "state": serialize_state()})

    if process and process.poll() is None:
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.kill(process.pid, signal.SIGTERM)
        except OSError as exc:
            append_log(f"停止任务失败：{exc}")

    with state_lock:
        state.running = False
        state.status = "stopped"
        state.finished_at = now_label()
        state.error = "任务已手动停止。"
        state.process = None

    return jsonify({"ok": True, "state": serialize_state()})


@app.get("/api/status")
def get_status():
    return jsonify(serialize_state())


@app.get("/download")
def download_output():
    with state_lock:
        output_path = Path(state.output_path) if state.output_path else None

    if not output_path or not output_path.exists():
        return jsonify({"ok": False, "error": "还没有可下载的 CSV。"}), 404

    return send_file(output_path, as_attachment=True, download_name=output_path.name)


@app.get("/download/verification")
def download_verification_queue():
    with state_lock:
        output_path = Path(state.verification_output_path) if state.verification_output_path else None

    if not output_path or not output_path.exists():
        return jsonify({"ok": False, "error": "还没有可下载的人工验证队列。"}), 404

    return send_file(output_path, as_attachment=True, download_name=output_path.name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
