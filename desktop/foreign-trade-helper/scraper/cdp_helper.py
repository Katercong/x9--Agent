from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
CDP_RUNTIME_PATH = ROOT / "data" / "runtime" / "chrome-cdp.json"


class TaskIn(BaseModel):
    platform: str = Field(pattern="^(qzrc_job|qzrc_resume|51job|51job_talent|zhaopin|zhaopin_resume)$")
    keywords: str = ""
    max_pages: int = Field(default=1, ge=1, le=100)
    max_items: int = Field(default=0, ge=0, le=5000)
    per_keyword_limit: int = Field(default=0, ge=0, le=5000)
    delay_min: float = Field(default=5.0, ge=0.5, le=120)
    delay_max: float = Field(default=8.0, ge=0.5, le=180)
    detail_delay_min: float = Field(default=6.0, ge=0.5, le=120)
    detail_delay_max: float = Field(default=10.0, ge=0.5, le=180)
    dry_run: bool = False
    inspect: bool = False
    needs_login: bool = False   # 兼容旧侧边栏字段；登录现在统一由“打开采集工作窗口”完成
    enrich: bool = False        # qzrc_job 是否带 --enrich（访问详情页补简介/地址）
    # ─── 列表采集节奏（默认 OFF；列表/API 风险较低）──
    batch_size: int = 0
    item_delay_min: float = 2.0
    item_delay_max: float = 5.0
    batch_delay_min: float = 0.0
    batch_delay_max: float = 0.0
    # ─── enrich 阶段节奏（默认标准节奏；详情页批量打开风险高）──
    enrich_batch_size: int = 0
    enrich_item_delay_min: float = 6.0
    enrich_item_delay_max: float = 10.0
    enrich_batch_delay_min: float = 0.0
    enrich_batch_delay_max: float = 0.0
    # ─── 通用 ──
    post_captcha_multiplier: float = 3.0
    stop_on_captcha: bool = False


@dataclass
class TaskState:
    id: str
    platform: str
    command: list[str]
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None
    returncode: int | None = None
    logs: list[str] = field(default_factory=list)
    progress: dict[str, Any] = field(default_factory=dict)


app = FastAPI(title="CompanyLeads CDP Helper", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TASKS: dict[str, TaskState] = {}
PROCS: dict[str, asyncio.subprocess.Process] = {}


def default_progress(task: TaskState) -> dict[str, Any]:
    return {
        "phase": task.status,
        "label": "等待开始" if task.status == "queued" else task.status,
        "current": 0,
        "total": 0,
        "percent": 0,
        "current_keyword": "",
        "current_page": None,
        "items_total": 0,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def merge_progress(task: TaskState, payload: dict[str, Any]) -> None:
    base = task.progress or default_progress(task)
    merged = {**base, **payload}
    try:
        current_n = float(merged.get("current") or 0)
        total_n = float(merged.get("total") or 0)
        if total_n > 0:
            merged["percent"] = max(0, min(100, round((current_n / total_n) * 100)))
        else:
            merged["percent"] = int(merged.get("percent") or 0)
    except Exception:
        merged["percent"] = int(merged.get("percent") or 0)
    merged["updated_at"] = datetime.now().isoformat(timespec="seconds")
    task.progress = merged


def apply_runtime_cdp_env(env: dict[str, str]) -> None:
    """Keep long-running helpers in sync with the latest Chrome CDP port."""
    if not CDP_RUNTIME_PATH.exists():
        return

    try:
        data = json.loads(CDP_RUNTIME_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return

    port = data.get("port")
    if port:
        env["COMPANYLEADS_CHROME_DEBUG_PORT"] = str(port)
        env["QCWY_CHROME_DEBUG_PORT"] = str(port)


def read_runtime_status() -> dict[str, Any]:
    if not CDP_RUNTIME_PATH.exists():
        return {}

    try:
        return json.loads(CDP_RUNTIME_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _append_pacing_args(cmd: list[str], payload: TaskIn, *, with_enrich_pacing: bool = False) -> None:
    """把节奏控制参数加到命令尾部。
    with_enrich_pacing=True 时附加 enrich-* 参数（qzrc_scraper / job_platform_scraper 都支持）。
    """
    # 列表节奏（只在用户显式开启时附加）
    if payload.batch_size > 0:
        cmd += ["--batch-size", str(payload.batch_size)]
    if payload.batch_delay_max > 0:
        cmd += [
            "--item-delay-min", str(payload.item_delay_min),
            "--item-delay-max", str(payload.item_delay_max),
            "--batch-delay-min", str(payload.batch_delay_min),
            "--batch-delay-max", str(payload.batch_delay_max),
        ]
    # 通用
    cmd += ["--post-captcha-multiplier", str(payload.post_captcha_multiplier)]
    if payload.stop_on_captcha:
        cmd.append("--stop-on-captcha")
    # enrich 节奏（详情页批量打开 — qzrc & 51job 都用）
    if with_enrich_pacing:
        cmd += [
            "--enrich-batch-size", str(payload.enrich_batch_size),
            "--enrich-item-delay-min", str(payload.enrich_item_delay_min),
            "--enrich-item-delay-max", str(payload.enrich_item_delay_max),
            "--enrich-batch-delay-min", str(payload.enrich_batch_delay_min),
            "--enrich-batch-delay-max", str(payload.enrich_batch_delay_max),
        ]


def build_command(payload: TaskIn) -> list[str]:
    if payload.platform in ("qzrc_job", "qzrc_resume"):
        mode = "job" if payload.platform == "qzrc_job" else "resume"
        cmd = [
            PYTHON,
            "scraper/qzrc_scraper.py",
            "--mode", mode,
            "--max-pages", str(payload.max_pages),
            "--max-items", str(payload.max_items),
            "--item-delay-min", str(payload.delay_min),
            "--item-delay-max", str(payload.delay_max),
        ]
        # Helper runs hidden from the user, so qzrc must never wait for terminal Enter.
        # The sidepanel opens the controlled Chrome window first when login is needed.
        cmd.append("--no-prompt")
        if payload.keywords.strip():
            cmd += ["--keywords", payload.keywords.strip()]
        if payload.dry_run:
            cmd.append("--dry-run")
        if payload.inspect:
            cmd.append("--inspect")
        if payload.enrich and mode == "job":
            cmd.append("--enrich")
        _append_pacing_args(cmd, payload, with_enrich_pacing=True)
        return cmd

    cmd = [
        PYTHON,
        "scraper/job_platform_scraper.py",
        "--platform", payload.platform,
        "--max-pages", str(payload.max_pages),
        "--max-items", str(payload.max_items),
        "--per-keyword-limit", str(payload.per_keyword_limit),
        "--delay-min", str(payload.delay_min),
        "--delay-max", str(payload.delay_max),
        "--detail-delay-min", str(payload.detail_delay_min),
        "--detail-delay-max", str(payload.detail_delay_max),
    ]
    if payload.keywords.strip():
        cmd += ["--keywords", payload.keywords.strip()]
    if payload.dry_run:
        cmd.append("--dry-run")
    if payload.inspect:
        cmd.append("--inspect")
    # job_platform_scraper 也支持双层节奏（list + enrich），enrich 阶段控制 51job 详情批次
    _append_pacing_args(cmd, payload, with_enrich_pacing=True)
    return cmd


async def run_task(task: TaskState) -> None:
    task.status = "running"
    task.started_at = datetime.now().isoformat(timespec="seconds")
    merge_progress(task, {"phase": "running", "label": "任务运行中"})
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    apply_runtime_cdp_env(env)

    try:
        proc = await asyncio.create_subprocess_exec(
            *task.command,
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        PROCS[task.id] = proc
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text.startswith("[PROGRESS] "):
                try:
                    progress_payload = json.loads(text[len("[PROGRESS] "):])
                    if isinstance(progress_payload, dict):
                        merge_progress(task, progress_payload)
                except Exception:
                    pass
            task.logs.append(text)
            if len(task.logs) > 800:
                task.logs = task.logs[-800:]
        task.returncode = await proc.wait()
        if task.status == "stopping":
            task.status = "stopped"
        else:
            task.status = "done" if task.returncode == 0 else "failed"
        merge_progress(
            task,
            {
                "phase": task.status,
                "label": "采集完成" if task.status == "done" else "采集失败",
                "percent": task.progress.get("percent", 0),
            },
        )
    except Exception as exc:
        if task.status != "stopping":
            task.status = "failed"
        task.logs.append(f"[HELPER-ERROR] {exc}")
        merge_progress(task, {"phase": "failed", "label": f"helper 异常: {exc}"})
    finally:
        PROCS.pop(task.id, None)
        task.finished_at = datetime.now().isoformat(timespec="seconds")


def task_dict(task: TaskState, *, include_logs: bool = False) -> dict[str, Any]:
    data = {
        "id": task.id,
        "platform": task.platform,
        "status": task.status,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "returncode": task.returncode,
        "command": task.command,
        "log_tail": task.logs[-20:],
        "progress": task.progress or default_progress(task),
    }
    if include_logs:
        data["logs"] = task.logs
    return data


@app.get("/health")
def health() -> dict[str, Any]:
    running = sum(1 for task in TASKS.values() if task.status in {"queued", "running", "stopping"})
    return {
        "ok": True,
        "productized": True,
        "version": "1.1.1",
        "python": PYTHON,
        "root": str(ROOT),
        "tasks": len(TASKS),
        "running_tasks": running,
        "runtime": read_runtime_status(),
    }


@app.get("/runtime/status")
def runtime_status() -> dict[str, Any]:
    return {"ok": True, "runtime": read_runtime_status()}


@app.post("/tasks")
async def create_task(payload: TaskIn) -> dict[str, Any]:
    task_id = uuid.uuid4().hex[:12]
    task = TaskState(id=task_id, platform=payload.platform, command=build_command(payload))
    TASKS[task_id] = task
    asyncio.create_task(run_task(task))
    return {"ok": True, "task": task_dict(task)}


@app.get("/tasks")
def list_tasks() -> dict[str, Any]:
    items = sorted(TASKS.values(), key=lambda t: t.created_at, reverse=True)
    return {"ok": True, "items": [task_dict(t) for t in items[:30]]}


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return {"ok": True, "task": task_dict(task, include_logs=True)}


@app.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str) -> dict[str, Any]:
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")

    if task.status not in {"queued", "running", "stopping"}:
        return {"ok": True, "task": task_dict(task, include_logs=True)}

    task.status = "stopping"
    task.logs.append("[HELPER] Stop requested by side panel.")
    proc = PROCS.get(task_id)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    if task.status == "stopping":
        task.status = "stopped"
    task.returncode = proc.returncode if proc else task.returncode
    task.finished_at = datetime.now().isoformat(timespec="seconds")
    merge_progress(task, {"phase": "stopped", "label": "采集已停止"})
    return {"ok": True, "task": task_dict(task, include_logs=True)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
