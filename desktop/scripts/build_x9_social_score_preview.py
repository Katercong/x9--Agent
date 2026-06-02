from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from desktop.backend.database.connection import SessionLocal  # noqa: E402
from desktop.backend.models.social_lead import (  # noqa: E402
    XhsAiJudgment,
    XhsExtractedContact,
    XhsUser,
    XhsUserHistoryPost,
    XhsUserSource,
)
from desktop.backend.services.xhs_lead_service import PROMPT_VERSION  # noqa: E402


EXPORT_DIR = ROOT / "desktop" / "data" / "exports" / "social_score_previews"

NON_TARGET_RELATIONSHIPS = {
    "consumer_buyer",
    "competitor_supplier",
    "service_provider",
    "risk_feedback",
    "irrelevant",
}
MAX_SCORE_BY_RELATIONSHIP = {
    "consumer_buyer": 35,
    "competitor_supplier": 45,
    "service_provider": 45,
    "cross_border_peer": 55,
    "risk_feedback": 30,
    "irrelevant": 30,
}
REQUIRED_AUDIT_FIELDS = (
    "target_user_utterance",
    "reply_context_interpretation",
    "identity_reasoning",
    "why_not_other_roles",
    "evidence_quotes",
    "evidence_chain_ids",
)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _as_int(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _audit_judgment(judgment: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    relationship = _text(judgment.get("relationship_type"))
    decision = _text(judgment.get("decision"))
    score = _as_int(judgment.get("fit_score"))

    def add(kind: str, message: str) -> None:
        issues.append({"kind": kind, "message": message})

    if decision == "high_priority" and relationship != "target_business_customer":
        add("matrix", f"high_priority 必须是 target_business_customer，当前为 {relationship or 'unknown'}")
    if decision == "follow_up" and relationship != "target_business_customer":
        add("matrix", f"follow_up 必须是 target_business_customer，当前为 {relationship or 'unknown'}")
    if relationship in NON_TARGET_RELATIONSHIPS and decision in {"high_priority", "follow_up"}:
        add("matrix", f"{relationship} 不能进入 {decision}")
    if relationship == "cross_border_peer" and decision in {"high_priority", "follow_up"}:
        add("matrix", "cross_border_peer 只能 nurture 或 ignore")
    if score is None:
        add("matrix", "fit_score 缺失或不是数字")
    else:
        if score < 0 or score > 100:
            add("matrix", f"fit_score 必须在 0-100，当前为 {score}")
        max_score = MAX_SCORE_BY_RELATIONSHIP.get(relationship)
        if max_score is not None and score > max_score:
            add("matrix", f"{relationship} 分数上限 {max_score}，当前为 {score}")
        if decision == "high_priority" and score < 70:
            add("matrix", f"high_priority 分数应 >=70，当前为 {score}")

    for field in REQUIRED_AUDIT_FIELDS:
        value = judgment.get(field)
        if field in {"evidence_quotes", "evidence_chain_ids"}:
            if not isinstance(value, list) or not value:
                add("structure", f"{field} 缺失或为空")
        elif not _text(value):
            add("structure", f"{field} 缺失")
    return issues


def _source_payload(source: XhsUserSource) -> dict[str, Any]:
    payload = _loads(source.source_payload, {})
    return payload if isinstance(payload, dict) else {}


def _build_rows(department_code: str, prompt_version: str) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        pairs = db.execute(
            select(XhsUser, XhsAiJudgment)
            .join(XhsAiJudgment, XhsAiJudgment.user_id == XhsUser.id)
            .where(
                XhsUser.department_code == department_code,
                XhsAiJudgment.department_code == department_code,
                XhsAiJudgment.prompt_version == prompt_version,
            )
            .order_by(XhsAiJudgment.created_at.desc())
        ).all()

        latest: dict[str, tuple[XhsUser, XhsAiJudgment]] = {}
        for user, judgment in pairs:
            latest.setdefault(user.id, (user, judgment))

        user_ids = list(latest.keys())
        contacts_by_user: dict[str, list[XhsExtractedContact]] = defaultdict(list)
        sources_by_user: dict[str, list[XhsUserSource]] = defaultdict(list)
        history_by_user: dict[str, list[XhsUserHistoryPost]] = defaultdict(list)
        if user_ids:
            for contact in db.scalars(
                select(XhsExtractedContact)
                .where(XhsExtractedContact.user_id.in_(user_ids))
                .order_by(XhsExtractedContact.created_at.desc())
            ):
                contacts_by_user[contact.user_id or ""].append(contact)
            for source in db.scalars(
                select(XhsUserSource)
                .where(XhsUserSource.user_id.in_(user_ids))
                .order_by(XhsUserSource.observed_at.desc(), XhsUserSource.created_at.desc())
            ):
                sources_by_user[source.user_id].append(source)
            for post in db.scalars(
                select(XhsUserHistoryPost)
                .where(XhsUserHistoryPost.user_id.in_(user_ids))
                .order_by(XhsUserHistoryPost.position.asc(), XhsUserHistoryPost.created_at.desc())
            ):
                history_by_user[post.user_id].append(post)

    rows: list[dict[str, Any]] = []
    for user, ai in latest.values():
        judgment = _loads(ai.judgment, {})
        if not isinstance(judgment, dict):
            judgment = {}
        if "user_key" not in judgment:
            judgment["user_key"] = user.id
        issues = _audit_judgment(judgment)
        sources = []
        for source in sources_by_user.get(user.id, [])[:8]:
            payload = _source_payload(source)
            sources.append(
                {
                    "source_type": source.source_type,
                    "keyword": source.keyword,
                    "evidence_text": source.evidence_text,
                    "evidence_url": source.evidence_url or payload.get("note_url"),
                    "comment_depth": source.comment_depth,
                    "note_title": payload.get("note_title"),
                    "note_url": payload.get("note_url"),
                    "published_at_text": payload.get("published_at_text"),
                    "location": payload.get("location"),
                }
            )
        rows.append(
            {
                "id": user.id,
                "platform": user.platform,
                "username": user.username_clean or user.username or user.username_raw or "未命名用户",
                "account": user.account_clean or user.account or user.external_user_id or user.xhs_user_id,
                "profile_url": user.canonical_profile_url or user.profile_url,
                "bio": user.bio_clean or user.bio or user.bio_raw,
                "location": user.location_text,
                "has_contact": bool(user.has_contact),
                "last_keyword": user.last_keyword,
                "fit_score": _as_int(ai.fit_score if ai.fit_score is not None else judgment.get("fit_score")) or 0,
                "fit_level": ai.fit_level or judgment.get("fit_level"),
                "decision": ai.decision or judgment.get("decision"),
                "intent_type": ai.intent_type or judgment.get("intent_type"),
                "relationship_type": judgment.get("relationship_type") or "unknown",
                "business_need_type": judgment.get("business_need_type") or "",
                "confidence": judgment.get("confidence"),
                "customer_priority": judgment.get("customer_priority") or "",
                "contact_priority": judgment.get("contact_priority") or "",
                "target_user_utterance": judgment.get("target_user_utterance") or judgment.get("evidence") or "",
                "reply_context_interpretation": judgment.get("reply_context_interpretation") or "",
                "identity_reasoning": judgment.get("identity_reasoning") or "",
                "why_not_other_roles": judgment.get("why_not_other_roles") or "",
                "reasons": _list(judgment.get("reasons")),
                "risks": _list(judgment.get("risks")),
                "evidence_quotes": _list(judgment.get("evidence_quotes")),
                "evidence_chain_ids": _list(judgment.get("evidence_chain_ids")),
                "recommended_action": judgment.get("recommended_action") or judgment.get("suggestion") or "",
                "created_at": ai.created_at,
                "issues": issues,
                "matrix_issue_count": sum(1 for issue in issues if issue["kind"] == "matrix"),
                "structure_issue_count": sum(1 for issue in issues if issue["kind"] == "structure"),
                "contacts": [
                    {
                        "type": contact.contact_type,
                        "value": contact.value_norm or contact.value_raw,
                        "source_field": contact.source_field,
                    }
                    for contact in contacts_by_user.get(user.id, [])[:6]
                ],
                "sources": sources,
                "history_posts": [
                    {
                        "title": post.title_clean or post.title_raw,
                        "url": post.canonical_note_url,
                        "like_count": post.like_count_text or post.like_count,
                        "published_at_text": post.published_at_text,
                    }
                    for post in history_by_user.get(user.id, [])[:8]
                ],
            }
        )

    rows.sort(key=lambda item: (item["fit_score"], item["created_at"] or ""), reverse=True)
    return rows


def _counter(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(_text(row.get(key)) or "unknown" for row in rows)
    return dict(counts.most_common())


def _matrix(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        out[_text(row.get("relationship_type")) or "unknown"][_text(row.get("decision")) or "unknown"] += 1
    return {rel: dict(decisions) for rel, decisions in out.items()}


def _summary(rows: list[dict[str, Any]], department_code: str, prompt_version: str) -> dict[str, Any]:
    scores = [int(row["fit_score"]) for row in rows]
    matrix_issues = sum(row["matrix_issue_count"] for row in rows)
    structure_issues = sum(row["structure_issue_count"] for row in rows)
    return {
        "department_code": department_code,
        "prompt_version": prompt_version,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(rows),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "high_priority": sum(1 for row in rows if row["decision"] == "high_priority"),
        "with_contact": sum(1 for row in rows if row["has_contact"]),
        "matrix_issue_count": matrix_issues,
        "structure_issue_count": structure_issues,
        "decision_counts": _counter(rows, "decision"),
        "relationship_counts": _counter(rows, "relationship_type"),
        "platform_counts": _counter(rows, "platform"),
        "score_level_counts": _counter(rows, "fit_level"),
        "matrix": _matrix(rows),
    }


def _html(data: dict[str, Any]) -> str:
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=_json_default).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X9 社媒线索评分预览</title>
  <style>
    :root {{
      --bg: #f4f1e8;
      --ink: #16130d;
      --muted: #6d6658;
      --line: #d4cab8;
      --paper: #fffdf7;
      --panel: #ebe4d7;
      --green: #237461;
      --green-soft: #d7ece5;
      --red: #b84f3d;
      --red-soft: #f3d7d0;
      --gold: #b88721;
      --gold-soft: #f2e3bb;
      --blue: #3b6386;
      --blue-soft: #dbe7ee;
      --shadow: 0 18px 42px rgba(51, 43, 30, .12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(22,19,13,.045) 1px, transparent 1px) 0 0 / 32px 32px,
        linear-gradient(0deg, rgba(22,19,13,.035) 1px, transparent 1px) 0 0 / 32px 32px,
        var(--bg);
      font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif;
      letter-spacing: 0;
    }}
    button, input, select {{ font: inherit; letter-spacing: 0; }}
    .shell {{ min-height: 100vh; padding: 24px; }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      padding-bottom: 18px;
      border-bottom: 2px solid var(--ink);
    }}
    h1 {{
      margin: 0;
      font-family: Georgia, "Noto Serif SC", serif;
      font-size: 34px;
      line-height: 1.08;
      font-weight: 700;
    }}
    .sub {{ margin-top: 8px; color: var(--muted); font-size: 13px; max-width: 920px; line-height: 1.6; }}
    .stamp {{ text-align: right; color: var(--muted); font-family: Consolas, monospace; font-size: 12px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ border: 1px solid var(--line); background: rgba(255,253,247,.92); padding: 13px; min-height: 92px; box-shadow: var(--shadow); }}
    .metric .label {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ margin-top: 10px; font-family: Georgia, serif; font-size: 32px; line-height: 1; font-weight: 700; }}
    .metric .hint {{ margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .layout {{ display: grid; grid-template-columns: 390px minmax(0, 1fr); gap: 14px; align-items: start; }}
    .rail, .main {{ border: 1px solid var(--line); background: rgba(255,253,247,.9); box-shadow: var(--shadow); }}
    .rail {{ position: sticky; top: 14px; max-height: calc(100vh - 28px); display: grid; grid-template-rows: auto auto 1fr; }}
    .filters {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 12px; border-bottom: 1px solid var(--line); }}
    .filters label:first-child {{ grid-column: 1 / -1; }}
    label.field {{ display: flex; align-items: center; gap: 8px; min-height: 38px; border: 1px solid var(--line); background: var(--paper); padding: 0 10px; }}
    .field span {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
    .field input, .field select {{ min-width: 0; width: 100%; border: 0; outline: 0; background: transparent; color: var(--ink); font-size: 13px; }}
    .charts {{ padding: 12px; border-bottom: 1px solid var(--line); display: grid; gap: 12px; }}
    .chart-title {{ display: flex; justify-content: space-between; align-items: baseline; font-weight: 700; font-size: 13px; }}
    .bar {{ display: grid; grid-template-columns: 110px minmax(0, 1fr) 38px; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; color: var(--muted); }}
    .track {{ height: 10px; background: var(--panel); border: 1px solid var(--line); overflow: hidden; }}
    .fill {{ height: 100%; width: var(--w); background: var(--green); }}
    .fill.red {{ background: var(--red); }}
    .fill.gold {{ background: var(--gold); }}
    .fill.blue {{ background: var(--blue); }}
    .list {{ overflow: auto; min-height: 0; }}
    .row {{ width: 100%; border: 0; border-bottom: 1px solid var(--line); background: transparent; color: var(--ink); text-align: left; padding: 12px; cursor: pointer; display: grid; gap: 8px; }}
    .row:hover, .row.active {{ background: #ece2cf; }}
    .row-top {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: start; }}
    .name {{ font-weight: 700; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }}
    .score {{ font-family: Georgia, serif; font-weight: 700; font-size: 22px; line-height: 1; }}
    .text {{ color: var(--muted); font-size: 12px; line-height: 1.55; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .chips {{ display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }}
    .chip {{ display: inline-flex; align-items: center; min-height: 22px; border: 1px solid var(--line); background: var(--paper); color: var(--muted); padding: 2px 7px; font-size: 11px; white-space: nowrap; }}
    .chip.red {{ background: var(--red-soft); color: #7b2e22; border-color: #df9f91; }}
    .chip.green {{ background: var(--green-soft); color: #145044; border-color: #8dc4b5; }}
    .chip.gold {{ background: var(--gold-soft); color: #6f4d08; border-color: #d9bf69; }}
    .chip.blue {{ background: var(--blue-soft); color: #284b68; border-color: #9bb6ca; }}
    .main {{ min-height: 620px; padding: 18px; }}
    .detail-head {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 16px; border-bottom: 1px solid var(--line); padding-bottom: 14px; margin-bottom: 14px; }}
    h2 {{ margin: 0; font-family: Georgia, "Noto Serif SC", serif; font-size: 30px; line-height: 1.14; }}
    .profile {{ margin-top: 8px; color: var(--muted); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }}
    .bigscore {{ min-width: 118px; border: 2px solid var(--ink); background: var(--paper); text-align: center; padding: 10px; }}
    .bigscore strong {{ display: block; font-family: Georgia, serif; font-size: 40px; line-height: 1; }}
    .bigscore span {{ display: block; margin-top: 6px; color: var(--muted); font-size: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .box {{ border: 1px solid var(--line); background: var(--paper); padding: 12px; min-width: 0; }}
    .box h3 {{ margin: 0 0 8px; font-size: 14px; }}
    .box p, .box li {{ margin: 0; font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; white-space: pre-wrap; }}
    .box ul {{ margin: 0; padding-left: 18px; }}
    .band {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--line); }}
    .source {{ border-left: 4px solid var(--green); background: var(--paper); border-top: 1px solid var(--line); border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 11px; margin-bottom: 9px; }}
    .source p {{ margin-top: 8px; color: var(--ink); font-size: 13px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .matrix {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    .matrix th, .matrix td {{ border: 1px solid var(--line); padding: 7px; text-align: left; }}
    .matrix th {{ background: var(--panel); color: var(--muted); }}
    a {{ color: var(--green); text-decoration: none; border-bottom: 1px solid currentColor; }}
    .empty {{ min-height: 420px; display: grid; place-items: center; color: var(--muted); }}
    @media (max-width: 1180px) {{
      .metrics {{ grid-template-columns: repeat(3, 1fr); }}
      .layout {{ grid-template-columns: 1fr; }}
      .rail {{ position: static; max-height: none; }}
    }}
    @media (max-width: 720px) {{
      .shell {{ padding: 14px; }}
      .hero, .detail-head, .grid, .metrics {{ grid-template-columns: 1fr; }}
      .stamp {{ text-align: left; }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <h1>X9 社媒线索评分预览</h1>
        <div class="sub">基于当前库中 foreign_trade 部门 98 个小红书/抖音社媒用户的最新链路意图评分。规则只看目标用户自己的证据，帖子和他人评论只作为上下文。</div>
      </div>
      <div class="stamp" id="stamp"></div>
    </section>
    <section class="metrics" id="metrics"></section>
    <section class="layout">
      <aside class="rail">
        <div class="filters">
          <label class="field"><span>搜索</span><input id="q" placeholder="用户 / 证据 / 理由 / 联系方式"></label>
          <label class="field"><span>判定</span><select id="decision"></select></label>
          <label class="field"><span>关系</span><select id="relationship"></select></label>
          <label class="field"><span>审计</span><select id="audit"></select></label>
          <label class="field"><span>排序</span><select id="sort"></select></label>
        </div>
        <div class="charts" id="charts"></div>
        <div class="list" id="list"></div>
      </aside>
      <main class="main" id="detail"></main>
    </section>
  </div>
  <script id="data" type="application/json">{embedded}</script>
  <script>
    const DATA = JSON.parse(document.getElementById('data').textContent);
    const rows = DATA.rows || [];
    const summary = DATA.summary || {{}};
    const state = {{ q: '', decision: 'all', relationship: 'all', audit: 'all', sort: 'score_desc', selected: 0 }};
    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    const labelMap = {{
      all: '全部',
      high_priority: '高优先',
      follow_up: '跟进',
      nurture: '观察',
      ignore: '忽略',
      target_business_customer: '目标客户',
      cross_border_peer: '跨境同行',
      service_provider: '服务商',
      competitor_supplier: '供应商同行',
      irrelevant: '无关',
      matrix: '硬规则问题',
      structure: '结构缺口',
      clean: '无审计问题',
      score_desc: '分数高到低',
      score_asc: '分数低到高',
      recent: '最新判定',
    }};
    function label(v) {{ return labelMap[v] || v || 'unknown'; }}
    function chip(v, tone='') {{ return `<span class="chip ${{tone}}">${{esc(label(v))}}</span>`; }}
    function tone(row) {{
      if (row.decision === 'high_priority') return 'red';
      if (row.decision === 'nurture') return 'gold';
      if (row.relationship_type === 'target_business_customer') return 'green';
      return 'blue';
    }}
    function fillSelect(id, values) {{
      const el = $(id);
      el.innerHTML = values.map(v => `<option value="${{esc(v)}}">${{esc(label(v))}}</option>`).join('');
      el.value = state[id];
      el.onchange = () => {{ state[id] = el.value; state.selected = 0; render(); }};
    }}
    function unique(key) {{ return ['all', ...Array.from(new Set(rows.map(r => r[key]).filter(Boolean))).sort()]; }}
    function setup() {{
      $('stamp').innerHTML = `department: ${{esc(summary.department_code)}}<br>prompt: ${{esc(summary.prompt_version)}}<br>generated: ${{esc(summary.generated_at)}}`;
      fillSelect('decision', unique('decision'));
      fillSelect('relationship', unique('relationship_type'));
      fillSelect('audit', ['all', 'matrix', 'structure', 'clean']);
      fillSelect('sort', ['score_desc', 'score_asc', 'recent']);
      $('q').oninput = (event) => {{ state.q = event.target.value.trim().toLowerCase(); state.selected = 0; render(); }};
      render();
    }}
    function renderMetrics() {{
      const items = [
        ['总用户', summary.total, `${{summary.with_contact}} 个有联系方式`],
        ['高优先', summary.high_priority, '可优先外呼'],
        ['平均分', summary.avg_score, `最高 ${{summary.max_score}}`],
        ['硬规则问题', summary.matrix_issue_count, '角色/决策矩阵'],
        ['结构缺口', summary.structure_issue_count, '多为 evidence_chain_ids'],
        ['评分版本', summary.prompt_version, summary.department_code],
      ];
      $('metrics').innerHTML = items.map(([label, value, hint]) => `<div class="metric"><div class="label">${{esc(label)}}</div><div class="value">${{esc(value)}}</div><div class="hint">${{esc(hint)}}</div></div>`).join('');
    }}
    function renderBars(title, counts, toneClass='green') {{
      const entries = Object.entries(counts || {{}});
      const max = Math.max(1, ...entries.map(([,v]) => Number(v) || 0));
      return `<div><div class="chart-title"><span>${{esc(title)}}</span><span>${{entries.reduce((s, [,v]) => s + Number(v || 0), 0)}}</span></div>` +
        entries.map(([k,v], i) => `<div class="bar"><span>${{esc(label(k))}}</span><div class="track"><div class="fill ${{i === 0 ? toneClass : ''}}" style="--w:${{Math.max(4, Math.round(v / max * 100))}}%"></div></div><b>${{v}}</b></div>`).join('') +
        `</div>`;
    }}
    function renderCharts() {{
      const decisions = summary.decision_counts || {{}};
      const relationships = summary.relationship_counts || {{}};
      const matrix = summary.matrix || {{}};
      const decisionKeys = Array.from(new Set(rows.map(r => r.decision).filter(Boolean))).sort();
      const matrixRows = Object.entries(matrix).map(([rel, cols]) =>
        `<tr><th>${{esc(label(rel))}}</th>${{decisionKeys.map(d => `<td>${{Number(cols[d] || 0)}}</td>`).join('')}}</tr>`
      ).join('');
      $('charts').innerHTML =
        renderBars('判定分布', decisions, 'red') +
        renderBars('关系类型', relationships, 'green') +
        `<div><div class="chart-title"><span>关系 x 判定矩阵</span></div><table class="matrix"><thead><tr><th>关系</th>${{decisionKeys.map(d => `<th>${{esc(label(d))}}</th>`).join('')}}</tr></thead><tbody>${{matrixRows}}</tbody></table></div>`;
    }}
    function filtered() {{
      let out = rows.filter(row => {{
        if (state.decision !== 'all' && row.decision !== state.decision) return false;
        if (state.relationship !== 'all' && row.relationship_type !== state.relationship) return false;
        if (state.audit === 'matrix' && !row.matrix_issue_count) return false;
        if (state.audit === 'structure' && !row.structure_issue_count) return false;
        if (state.audit === 'clean' && (row.matrix_issue_count || row.structure_issue_count)) return false;
        if (!state.q) return true;
        const hay = [
          row.username, row.account, row.bio, row.target_user_utterance, row.identity_reasoning,
          row.reply_context_interpretation, row.recommended_action, JSON.stringify(row.contacts),
          JSON.stringify(row.sources), JSON.stringify(row.evidence_quotes)
        ].join(' ').toLowerCase();
        return hay.includes(state.q);
      }});
      if (state.sort === 'score_asc') out = out.sort((a,b) => a.fit_score - b.fit_score);
      else if (state.sort === 'recent') out = out.sort((a,b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
      else out = out.sort((a,b) => b.fit_score - a.fit_score);
      return out;
    }}
    function renderList(items) {{
      if (!items.length) {{
        $('list').innerHTML = '<div class="empty">没有匹配的线索</div>';
        return;
      }}
      if (state.selected >= items.length) state.selected = 0;
      $('list').innerHTML = items.map((row, i) => `
        <button class="row ${{i === state.selected ? 'active' : ''}}" data-index="${{i}}">
          <div class="row-top"><div class="name">${{esc(row.username)}}</div><div class="score">${{row.fit_score}}</div></div>
          <div class="chips">
            ${{chip(row.decision, tone(row))}}
            ${{chip(row.relationship_type, row.relationship_type === 'target_business_customer' ? 'green' : 'blue')}}
            ${{row.matrix_issue_count ? chip('硬规则问题', 'red') : ''}}
            ${{row.structure_issue_count ? chip('结构缺口', 'gold') : ''}}
          </div>
          <div class="text">${{esc(row.target_user_utterance || row.bio || '暂无证据摘要')}}</div>
        </button>
      `).join('');
      $('list').querySelectorAll('.row').forEach(btn => btn.onclick = () => {{ state.selected = Number(btn.dataset.index); render(); }});
    }}
    function listHtml(items) {{
      if (!Array.isArray(items) || !items.length) return '<p>-</p>';
      return `<ul>${{items.map(item => `<li>${{esc(item)}}</li>`).join('')}}</ul>`;
    }}
    function box(title, body) {{ return `<section class="box"><h3>${{esc(title)}}</h3>${{body}}</section>`; }}
    function renderSources(row) {{
      if (!row.sources?.length) return '<div class="source"><p>暂无来源证据</p></div>';
      return row.sources.map(source => `
        <article class="source">
          <div class="chips">
            ${{chip(source.source_type || 'source', 'green')}}
            ${{source.comment_depth !== null && source.comment_depth !== undefined ? chip('depth ' + source.comment_depth, 'blue') : ''}}
            ${{source.keyword ? chip(source.keyword, 'gold') : ''}}
          </div>
          <p>${{esc(source.evidence_text || '-')}}</p>
          <div class="text">
            ${{esc(source.note_title || '')}}
            ${{source.note_url ? ` · <a href="${{esc(source.note_url)}}" target="_blank" rel="noreferrer">打开帖子</a>` : ''}}
          </div>
        </article>
      `).join('');
    }}
    function renderDetail(row) {{
      const contacts = row.contacts?.map(c => `${{c.type}}: ${{c.value}}`).filter(Boolean) || [];
      const issues = row.issues?.map(i => `[${{i.kind}}] ${{i.message}}`) || [];
      const history = row.history_posts?.map(p => p.url ? `${{p.title || '-'}} · ${{p.url}}` : (p.title || '-')) || [];
      $('detail').innerHTML = `
        <div class="detail-head">
          <div>
            <h2>${{esc(row.username)}}</h2>
            <div class="profile">${{esc(row.platform || '')}} · 账号 ${{esc(row.account || '-')}} · ${{row.profile_url ? `<a href="${{esc(row.profile_url)}}" target="_blank" rel="noreferrer">打开主页</a>` : '无主页链接'}}</div>
            <div class="chips" style="margin-top:10px">
              ${{chip(row.decision, tone(row))}}
              ${{chip(row.relationship_type, row.relationship_type === 'target_business_customer' ? 'green' : 'blue')}}
              ${{chip(row.intent_type || 'unknown')}}
              ${{row.has_contact ? chip('有联系方式', 'green') : chip('无联系方式', 'gold')}}
            </div>
          </div>
          <div class="bigscore"><strong>${{row.fit_score}}</strong><span>${{esc(row.fit_level || '-')}} · ${{esc(row.customer_priority || '-')}}</span></div>
        </div>
        <div class="grid">
          ${{box('目标用户本人证据', `<p>${{esc(row.target_user_utterance || '-')}}</p>`)}}
          ${{box('身份推理', `<p>${{esc(row.identity_reasoning || '-')}}</p>`)}}
          ${{box('上下文解释', `<p>${{esc(row.reply_context_interpretation || '-')}}</p>`)}}
          ${{box('不是其他角色的原因', `<p>${{esc(row.why_not_other_roles || '-')}}</p>`)}}
          ${{box('判定理由', listHtml(row.reasons))}}
          ${{box('风险 / 审计提示', listHtml([...(row.risks || []), ...issues]))}}
          ${{box('证据引用', listHtml(row.evidence_quotes))}}
          ${{box('联系方式', listHtml(contacts))}}
        </div>
        <section class="band">
          <h3>来源证据</h3>
          ${{renderSources(row)}}
        </section>
        <section class="band grid">
          ${{box('建议动作', `<p>${{esc(row.recommended_action || '-')}}</p>`)}}
          ${{box('主页历史作品', listHtml(history))}}
        </section>
      `;
    }}
    function render() {{
      renderMetrics();
      renderCharts();
      const items = filtered();
      renderList(items);
      if (items.length) renderDetail(items[state.selected]);
      else $('detail').innerHTML = '<div class="empty">没有可展示的线索</div>';
    }}
    setup();
  </script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static preview for X9 social chain-intent scores.")
    parser.add_argument("--department-code", default="foreign_trade")
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    parser.add_argument("--output-dir", type=Path, default=EXPORT_DIR)
    args = parser.parse_args()

    rows = _build_rows(args.department_code, args.prompt_version)
    data = {
        "summary": _summary(rows, args.department_code, args.prompt_version),
        "rows": rows,
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base = f"x9_social_score_preview_{args.department_code}_{args.prompt_version}_{stamp}"
    json_path = args.output_dir / f"{base}.json"
    html_path = args.output_dir / f"{base}.html"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    html_path.write_text(_html(data), encoding="utf-8")
    print(json.dumps({"json": str(json_path.resolve()), "html": str(html_path.resolve()), "summary": data["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
