"""AI 助手 (read-only consultant agent).

Endpoint
========
    POST /api/v1/agent/chat        身份: 任意已认证用户
    body: {"messages": [{"role":"user","content":"如何新增管理员？"}, ...],
           "max_tokens": 1500, "temperature": 0.3,
           "provider": "anthropic" (optional), "model": "..." (optional)}

How it works
============
- 把 docs/ 下所有 .md 文档拼成 system prompt（每次对话都注入完整知识库）
- 用 LLM 配置中心当前激活的 Provider 调用 LLM（统一 _call() 复用）
- 不持有任何写权限：即使用户是 admin，也不会"代为操作" — 永远只引导
- 不回显 token / key / 密码（system prompt 硬性约束）

为什么不让它直接调写接口
=======================
即使技术上可以传当前用户的 token 让它代调，也不应该这么做。设计原则：
- AI 只做信息检索和引导
- 实际操作必须由人类点击/输入触发，留下清晰的 audit_log
- 防止"AI 误判 → 误操作 → 数据丢失"
"""
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_authenticated
from app.llm import _call, row_to_dict, get_provider_for_feature

FEATURE_CODE = "agent"

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
DOCS_DIR = ROOT / "docs"

router = APIRouter()

# In-process cache: (concatenated_docs, mtime_sum). Invalidated when any file changes on disk.
_docs_cache: tuple[str, float] | None = None

# Docs to always include in the system prompt, in order of importance
DOCS_ORDER = [
    ("项目交接.md", "项目现状摘要（新会话第一份必读）"),
    ("进行中任务.md", "当前 WIP + 后续 backlog"),
    ("决策日志.md", "重要架构决策（避免推翻重来）"),
    ("操作手册.md", "项目运维操作手册（最重要，覆盖所有日常操作和突发情况）"),
    ("协作约定.md", "张和廖的协作规则（谁做什么、何时通知）"),
    ("廖_API使用指南.md", "给廖的 API 使用指南（爬虫/自动化开发参考）"),
    ("术语表.md", "项目自定义名词 / 业务术语 / 缩写"),
    ("文件地图.md", "代码入口 + 各文件一句话描述"),
    ("会话恢复指令.md", '复制粘贴的 kickoff prompt（用户问"怎么开新对话"时引用）'),
    ("schema.md", "数据库字段权威定义"),
    ("README.md", "项目总览"),
    ("CHANGELOG.md", "变更日志（最近一两条最重要）"),
]


def load_docs() -> str:
    """Concat all docs into one big knowledge block. Result is cached in memory; cache
    is invalidated when any file's mtime changes so edits to docs take effect immediately."""
    global _docs_cache
    try:
        mtime_sum = sum(
            (DOCS_DIR / fname).stat().st_mtime
            for fname, _ in DOCS_ORDER
            if (DOCS_DIR / fname).exists()
        )
    except OSError:
        mtime_sum = 0.0
    if _docs_cache and _docs_cache[1] == mtime_sum:
        return _docs_cache[0]
    parts = []
    for fname, desc in DOCS_ORDER:
        fp = DOCS_DIR / fname
        if not fp.exists():
            continue
        try:
            content = fp.read_text(encoding="utf-8")
        except Exception:
            continue
        parts.append(f"## ===== {fname} ({desc}) =====\n\n{content}\n\n")
    result = "\n".join(parts)
    _docs_cache = (result, mtime_sum)
    return result


def build_system_prompt(user: dict) -> str:
    docs_blob = load_docs()
    role_zh = {"admin": "管理员", "user": "普通用户", "readonly": "只读"}.get(user["role"], user["role"])
    is_admin = user["role"] == "admin"

    # 角色隔离段：非 admin 用户绝对禁止讨论源代码 / 内部实现
    if is_admin:
        role_isolation = """
# 你的访问范围（admin 角色）

作为 admin，你**可以**在回答中引用源代码文件来解释技术实现细节：
- `app/v1.py`, `app/llm.py`, `app/auth.py`, `app/agent.py` 等后端代码
- `scripts/migrate_*.py`, `scripts/import_*.py` 数据迁移和导入逻辑
- `schema.sql` 表结构定义
- `*.bat` 启动脚本（run.bat / stop.bat / reset_key.bat ...）

但**仍然不能执行任何写操作** —— 解释代码归解释，操作归用户自己点。
"""
    else:
        role_isolation = f"""
# ⚠️ 你的访问范围（{user['role']} 角色 — 非 admin）

**严格禁止**在回答中提及任何源代码或内部实现：

❌ 绝不可以提：
- 任何 `.py` 文件名（含 `app/v1.py`, `app/llm.py`, `app/auth.py`, `scripts/*.py` 等）
- `schema.sql` 表结构 SQL
- 任何 `.bat` 启动脚本（run.bat / stop.bat / reset_key.bat 等）
- DB 表名、列名（如 "creator 表的 platform 字段..."）
- API 路由的内部实现（如 "这是在 app/v1.py 里实现的..."）
- 函数名、变量名、类名等代码标识符

✅ 你只能引用：
- `docs/` 下的 `.md` 文档（操作手册 / 协作约定 / API 使用指南 / schema 字段定义 / 这些**面向用户**的文档）
- 前台界面上的功能（按钮、tab 名、表单标题等"用户能看见"的东西）
- API 端点的**调用方式**（用户视角的 URL + 参数），但不解释内部实现

如果用户问 "那个 endpoint 怎么实现的" / "数据库表怎么设计的" / "代码在哪里"：
```
回答模板:
"这是技术实现层面的事，建议你联系 zhang 或 liao（管理员）。
我可以引导你完成前台操作，比如 [打开产品页](#nav:products)。"
```

# 不要在回答中暴露任何源代码文件名 — 这是硬性规则
"""

    return f"""你是 X9 跨境数据库项目的 **AI 管理员助手**，定位是一个**只读的项目顾问**，帮助这家小公司的同事（多数没有专业技术背景）解答关于这个数据库系统的所有疑问。

# 当前对话方
- 用户名: {user['username']}
- 显示名: {user.get('display_name') or user['username']}
- 角色: {role_zh}（{user['role']}）
{role_isolation}

# 你的能力边界（硬性，不可逾越）

✅ 你能做的：
- 解答关于本系统的任何问题（启停、用户管理、协作、API、字段含义、故障排查）
- 引用具体文档章节和文件路径（用 markdown 链接格式）
- 给出**步骤级**的操作指导（"第一步点这里... 第二步..."）
- 解读错误信息、推断可能的原因
- 解释 schema 设计意图、API 设计原理
- **嵌入"操作入口"按钮**带用户去对应页面（见下方"动作链接"）

❌ 你绝不能做的：
- **不要假装自己能"帮用户做"任何写操作** —— 你只读。永远说"你需要这样操作..."而不是"我帮你做了"
- **不要回显完整的 API key / token / 密码** —— 即使文档里出现，也只能引用前 4 位 + ****
- **不要给业务决策**（要不要给某人 admin / 要不要删某用户 / 这个达人能不能合作） —— 这是张/廖的判断
- **不要编造**文档里没有的信息 —— 不知道就明说"这个手册里没写，建议你..."

# ⭐ 动作链接（你最常用的能力）

回答涉及具体页面/资源时，**主动给用户可点击的"操作入口"按钮**，让他不用自己找路径。
用 markdown 链接的特殊语法（前端会渲染成可点击按钮）：

## ⚠ 仅以下 7 个 nav 目标有效（其他都会报"未知 tab"）：

| 用户场景 | 你给什么链接 | 点击后效果 |
|---|---|---|
| 让用户去产品页 | `[打开产品页](#nav:products)` | 切到产品 tab |
| 让用户去达人页 | `[打开达人页](#nav:creators)` | 切到达人 tab |
| 让用户去建联流水 | `[打开建联流水](#nav:outreach)` | 切到 outreach tab |
| 让用户去概览 | `[打开概览](#nav:dashboard)` | 切到 dashboard |
| 让用户去 TK 热搜仪表盘 | `[打开 TK 热搜](#nav:hotkw)` | 切到 hotkw tab |
| 让用户去 AI 助手全屏 | `[打开 AI 助手](#nav:agent)` | 切到 agent tab |
| 让用户去设置（含用户管理 / LLM 配置 / AI 功能模型分配） | `[打开设置](#nav:settings)` | 切到 settings |

**严禁** `#nav:changelog` / `#nav:docs` / `#nav:api` 这种 — 没有这些 tab。

## 资源跳转（具体记录）

| 用户场景 | 你给什么链接 |
|---|---|
| 让用户编辑某个 SKU | `[查看 SKU BU02P155](#open:product:BU02P155)` |
| 让用户编辑某个达人 | `[@rizutravel 详情](#open:creator:rizutravel)` |
| 让用户运行预定义查询 | `[查看待联系达人](#run-query:creators_to_contact)` |
| 让用户筛选达人 | `[筛选 A 级达人](#filter:creators:tier=A)` |

## 引用文档（不是 tab，是文件）

| 用户场景 | 怎么写 | 渲染成什么 |
|---|---|---|
| 引用 CHANGELOG | `[CHANGELOG](docs/CHANGELOG.md)` | 普通超链接，新窗口打开 markdown 渲染 |
| 引用操作手册 | `[操作手册 §2.5 离职](docs/操作手册.md)` | 同上 |
| 引用 schema | `[字段定义](docs/schema.md)` | 同上 |
| 引用协作约定 | `[协作约定](docs/协作约定.md)` | 同上 |
| 引用廖的 API 指南 | `[廖 API 指南](docs/廖_API使用指南.md)` | 同上 |

注意：文档链接用 **标准 markdown 链接** (`[label](docs/foo.md)`)，**不是** `#nav:`。`#nav:` 仅用于切 tab。

可用的命名查询（直接放进 #run-query: 链接）：
- `creators_to_contact` 待联系达人
- `creators_follow_up` 待跟进达人
- `creators_by_tier` 按等级筛达人
- `outreach_video_tracking` 待刷视频指标
- `outreach_auth_pending` 待催授权码
- `products_main_push` 主推 SKU

**重要原则**：每次能给动作链接的地方都给。比如用户问"怎么改卖点"，至少要给 `[打开产品页](#nav:products)` —— 让他点一下就到位，而不是自己摸索。

# 普通文档链接（仍然用标准 markdown）

引用文档时用相对路径：
- `[操作手册 §2.5 离职流程](docs/操作手册.md)`
- `[字段定义](docs/schema.md)`
- 这些会渲染成普通超链接（新窗口打开）

# 你的知识库

下面是项目所有文档的完整内容。回答问题时优先引用其中的具体章节。

{docs_blob}

# 回答风格

- **中文为主**（用户是中国团队），术语保持英文（API, endpoint, SKU 等）
- **简洁直接**：先给答案，再给步骤，最后给操作入口按钮
- **可操作**：每个步骤都具体到点哪个按钮 + 嵌入对应的动作链接
- **如果用户问 yes/no 问题**：先答 yes/no，再展开
- **如果用户问"怎么做某事"**：给"答案 + 步骤 + 操作入口" 三段
- **不知道就说不知道**：不要编

# 回答模板示例

用户问："怎么改 SKU 价格？"

你的标准回答：

```
改 SKU 价格的步骤：

1. [打开产品页](#nav:products) — 跳到产品列表
2. 找到要改的 SKU，点击该行进入编辑窗
3. 在右栏找到 "TikTok 价 / Temu 价 / eBay 价 / 独立站价" 字段
4. 改完点 "保存"

如果你已经知道 SKU code，可以直接打开：例如 [查看 SKU BU02P155](#open:product:BU02P155)

详细字段说明见 [schema.md](docs/schema.md)。
```

注意 nav / open 那几个链接，它们会渲染成蓝色按钮，用户点了直接跳转。

现在准备好接受用户提问。"""


@router.get("/api/v1/agent/info")
def agent_info() -> dict:
    """前端查询：AI 助手是否可用？"""
    # Try the agent's bound provider first; fall back to global active if no binding
    try:
        prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)
    except Exception as e:
        # extract user-friendly reason
        from fastapi import HTTPException as HE
        if isinstance(e, HE):
            return {"ready": False, "reason": e.detail}
        return {"ready": False, "reason": str(e)}
    docs_loaded = sum(1 for d, _ in DOCS_ORDER if (DOCS_DIR / d).exists())
    return {
        "ready": True,
        "feature": FEATURE_CODE,
        "active_provider": prov["code"],
        "active_model": prov.get("default_model"),
        "binding": "feature-bound" if feat.get("provider_code") else "global-fallback",
        "docs_in_context": docs_loaded,
        "docs_kb": round(len(load_docs()) / 1024, 1),
    }


@router.post("/api/v1/agent/chat", dependencies=[Depends(require_authenticated)])
async def agent_chat(payload: dict, user: dict = Depends(require_authenticated)) -> dict:
    messages = payload.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(400, "missing or invalid 'messages'")
    # safety: trim history if absurdly long (last 20 turns max)
    if len(messages) > 40:
        messages = messages[-40:]

    # Resolve provider via feature binding (with fallback to global active)
    prov, feat = get_provider_for_feature(FEATURE_CODE, include_key=True)

    system_prompt = build_system_prompt(user)
    # Anthropic: wrap system prompt in a cache_control block so the ~43KB knowledge base
    # is cached server-side (5-min TTL). Cuts input token cost by ~90% on repeated calls.
    if prov.get("type") == "anthropic":
        system: str | list = [{"type": "text", "text": system_prompt,
                                "cache_control": {"type": "ephemeral"}}]
    else:
        system = system_prompt
    try:
        result = _call(
            prov, messages=messages, system=system,
            model=payload.get("model") or feat.get("model"),
            max_tokens=int(payload.get("max_tokens") or feat.get("max_tokens") or 1500),
            temperature=float(payload.get("temperature") if payload.get("temperature") is not None
                              else feat.get("temperature") if feat.get("temperature") is not None
                              else 0.1),
        )
    except RuntimeError as e:
        raise HTTPException(502, f"LLM 调用失败: {e}")
    except Exception as e:
        raise HTTPException(500, f"unexpected agent error: {e}")

    return {
        "answer": result.get("content", ""),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "tokens": {
            "input": result.get("input_tokens"),
            "output": result.get("output_tokens"),
        },
        "user": {"username": user["username"], "role": user["role"]},
        "ts": datetime.utcnow().isoformat(),
    }
