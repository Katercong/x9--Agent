"""Compatibility namespace for pre-merge desktop imports.

The project now lives under ``desktop.backend``. Older tests and docs still
refer to ``x9_creator_desktop_system.backend``, so keep that import path alive.
"""

from __future__ import annotations

import importlib
import sys

backend = importlib.import_module("desktop.backend")
sys.modules.setdefault(__name__ + ".backend", backend)

