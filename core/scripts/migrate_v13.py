"""migrate_v13 — api_key.scopes 字段（key 分级权限，P3 #9）

给 api_key 加 scopes 列（TEXT，JSON array）。
NULL = 走老的 role 三档（admin/user/readonly），完全向后兼容。

scope 字符串格式：
  'admin'             — 所有操作所有资源
  'admin:<pattern>'   — admin 权限限定到匹配 pattern 的资源
  'write:<pattern>'   — 写权限限定到匹配 pattern 的资源
  'read:<pattern>'    — 读权限限定（当前 GET 公开，仅未来用）

pattern 用 fnmatch，'*' = 任意，'tk_*' = 前缀匹配。

举例：
  ['write:tk_*']                  — 只能 bulk/patch/delete tk_* 开头的资源
  ['admin:tk_*', 'read:*']        — tk_* 全权限 + 全部读权限
  ['admin']                       — 同 admin 角色
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "database.db"


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(api_key)")}
        if "scopes" not in cols:
            con.execute("ALTER TABLE api_key ADD COLUMN scopes TEXT")
            con.commit()
            print("[migrate_v13] added api_key.scopes column (NULL = legacy role-based)")
        else:
            print("[migrate_v13] api_key.scopes already exists")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
