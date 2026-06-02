"""Background auto scoring for foreign-trade social leads."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Iterable

from ..database import SessionLocal
from ..services.xhs_lead_service import auto_judge_unjudged_social

log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()
_SCORE_LOCK = threading.Lock()
_WAKE_EVENT = threading.Event()
_REQUESTED_DEPARTMENTS: set[str | None] = set()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _default_department() -> str | None:
    raw = os.getenv("X9_FT_AUTO_JUDGE_DEPARTMENT", "foreign_trade").strip()
    return raw or None


def request_auto_score(department_code: str | None = None) -> None:
    with _LOCK:
        _REQUESTED_DEPARTMENTS.add(department_code or _default_department())
    _WAKE_EVENT.set()


def _pop_requested_departments() -> set[str | None]:
    with _LOCK:
        departments = set(_REQUESTED_DEPARTMENTS)
        _REQUESTED_DEPARTMENTS.clear()
    return departments or {_default_department()}


def _run_once(departments: Iterable[str | None] | None = None) -> list[dict]:
    if not _SCORE_LOCK.acquire(blocking=False):
        return []
    results: list[dict] = []
    try:
        for department_code in departments or _pop_requested_departments():
            try:
                with SessionLocal() as db:
                    result = auto_judge_unjudged_social(db, department_code=department_code)
                results.append({"department_code": department_code, **result})
                pending = int(result.get("pending") or 0)
                judged = int(result.get("judged") or 0)
                if pending or judged:
                    log.info(
                        "foreign_trade_scoring_scheduler: department=%s pending=%d judged=%d ok=%s",
                        department_code or "all",
                        pending,
                        judged,
                        result.get("ok"),
                    )
            except Exception as exc:  # noqa: BLE001 - background scoring must not crash the app
                log.warning("foreign_trade_scoring_scheduler: scoring failed for %s: %s", department_code or "all", exc)
                results.append({"department_code": department_code, "ok": False, "error": str(exc)[:300]})
        return results
    finally:
        _SCORE_LOCK.release()


def _run() -> None:
    startup_delay = max(0.0, _env_float("X9_FT_AUTO_JUDGE_STARTUP_DELAY_SECONDS", 5.0))
    interval = max(5.0, _env_float("X9_FT_AUTO_JUDGE_INTERVAL_SECONDS", 60.0))
    if startup_delay:
        time.sleep(startup_delay)
    while True:
        _run_once()
        _WAKE_EVENT.wait(interval)
        _WAKE_EVENT.clear()


def start_foreign_trade_auto_scoring() -> None:
    if _env_bool("X9_FT_AUTO_JUDGE_DISABLED", False):
        log.info("foreign_trade_scoring_scheduler: disabled by X9_FT_AUTO_JUDGE_DISABLED")
        return
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_run, daemon=True, name="foreign-trade-auto-scoring")
    thread.start()
    log.info("foreign_trade_scoring_scheduler: started auto scoring thread")
