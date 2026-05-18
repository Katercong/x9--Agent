# X9 Creator Desktop System (v3)

## Strict v1.0.19 auto-collection flow (recommended)

The original v1.0.19 extension at
`F:\AI Agent\Auto boker grab\tiktok-creator-lead-browser-extension-1.0.19.zip`
already has a full working auto-run loop: keyword → search → scroll →
open profile → scrape → filter → save → next, with rate limiting and
rest breaks. **None of its source files are modified.** We only add a
two-file relay that listens to its existing `chrome.storage.tclabState`
and forwards each finished creator to the local v3 backend.

```powershell
cd "F:\AI Agent\Auto boker grab\x9_creator_desktop_system"
powershell -ExecutionPolicy Bypass -File scripts\install_extension_strict.ps1
```

What the installer does:
1. Unzips `tiktok-creator-lead-browser-extension-1.0.19.zip` into
   `chrome-extension/` verbatim. **No source file is patched.**
2. Drops in two new files:
   * `x9_sw.js` — service-worker shim that `importScripts()` loads
     `background.js` (original) + `x9_relay.js` (new).
   * `x9_relay.js` — listens to `chrome.storage.onChanged` for
     `tclabState`, diffs leads/skipped against what was already sent,
     and POSTs only the **newly finished** records to the v3 backend.
     Also pushes a launcher heartbeat every 8 s so the dashboard's
     Collection Monitor shows live counters.
3. Patches `manifest.json`:
   * `background.service_worker` → `x9_sw.js`
   * `host_permissions` += `http://127.0.0.1:8000/*` and `http://localhost:8000/*`
   * `permissions` += `alarms` (the relay uses `chrome.alarms`)

Nothing else changes. The extension's UI, search box, scroll behaviour,
profile scraping, filter rules, exports, counters and timer are the
v1.0.19 originals.

### What gets relayed and when

| When | What | To |
|---|---|---|
| Every time `tclabState.leads` grows (a creator passes filters) | The new lead, in v1.0.19's exact `buildX9CreatorIngestItem` shape | `POST /api/local/extension/x9-compat/ingest-creators` |
| Every time `tclabState.skippedProfiles` grows (a creator was rejected) | The skipped record (with `current_status: dropped`) | same endpoint |
| On every storage change + every 8 s | counts / runTimer / activeTab / settings | `POST /api/local/extension/launcher-heartbeat` |

The relay never sends the same lead twice — it tracks a hash set of
already-relayed `(profile_url, username, email)` triples in
`chrome.storage.local.x9_relayed_keys`.

### Old workflow you may have used (rewrite-style)

If you previously ran `install_extension_from_v1_19.ps1` (which copied
the source files and patched URL constants inside `popup.js`), that
script still exists for reference but `install_extension_strict.ps1` is
the one to use going forward — it doesn't touch any v1.0.19 file.

What the installer does:
1. Copies `manifest.json`, `background.js`, `contentScript.js`,
   `popup.html`, `popup.css`, `popup.js`, `sidepanel.html` from the
   v1.0.19 folder into `x9_creator_desktop_system/chrome-extension/`.
2. Patches just four URL constants in `popup.js`:
   - `X9_API_BASE_URL` → `http://127.0.0.1:8000`
   - `X9_API_KEY` → `""` (the v3 local backend does not require a key)
   - `X9_CREATOR_INGEST_URL` →
     `http://127.0.0.1:8000/api/local/extension/x9-compat/ingest-creators`
   - `LAUNCHER_HEARTBEAT_URL` →
     `http://127.0.0.1:8000/api/local/extension/launcher-heartbeat`
3. Updates `manifest.json` `host_permissions` so the extension is allowed
   to talk to `127.0.0.1:8000`.

Nothing else in `popup.js` is changed — the auto-run loop, search
orchestration, scroll logic, profile collector, filter rules, exports,
counters and timer are all the v1.0.19 originals.

### v3 backend endpoints that accept the v1.0.19 payloads

| v1.0.19 caller | v3 endpoint | What it does on the dashboard |
|---|---|---|
| `syncCreatorToX9Database()` | `POST /api/local/extension/x9-compat/ingest-creators` | Each `items[]` entry becomes a `creator_observation`, runs through `collector_service`, gets scored/tagged/recommended on the next pipeline run, and shows up in `Creator Recommendations` |
| `sendLauncherHeartbeat()` | `POST /api/local/extension/launcher-heartbeat` | Upserts `extension_sessions` (so `/extension/status` shows online) **and** `extension_run_progress` (so `Collection Monitor` shows live counters: leads, pending, skipped, elapsed, current step) |

The backend translates the legacy fields automatically — `notes="keyword=… filter=… message=…"` is parsed back into structured search_keyword + filter_reason; `current_status="dropped"` is preserved as a flag on the response so you can audit which creators the extension itself rejected before they ever reach scoring.

### Running it

```powershell
cd "F:\AI Agent\Auto boker grab\x9_creator_desktop_system"

# 1. Migrate / start backend
py -3.11 -m x9_creator_desktop_system.backend.migrations.001_init
.\start_desktop.bat

# 2. (One-time) install the v1.0.19 flow into the v3 chrome-extension folder
powershell -ExecutionPolicy Bypass -File scripts\install_extension_from_v1_19.ps1

# 3. chrome://extensions → Load unpacked → pick chrome-extension/
#    Pin the icon → Open side panel
# 4. Open TikTok, log in, set search keyword in the side panel
# 5. Click Start Auto Run — exactly as in v1.0.19
# 6. Open http://127.0.0.1:8000/ui/ → Collection Monitor
#    Live counters update from the launcher-heartbeat stream.
```

Tests for the compat layer:

```powershell
py -3.11 -m pytest x9_creator_desktop_system/backend/tests/test_v1_19_compat.py -v
```

---


Desktop-controlled local pipeline for collecting, scoring, tagging,
recommending and routing TikTok creator leads against the X9 product
catalog (feminine care, pet care, home care, adult care, mom & baby,
health mask).

```
chrome-extension/  ← lightweight DOM scraper + heartbeat
       │ HTTP
       ▼
backend/           ← FastAPI + SQLite + scoring + recommendation
       │ HTTP
       ▼
desktop/           ← Electron shell (or run in browser)
```

## Roles by component

* **Chrome extension** detects TikTok page state, sends a heartbeat
  every 5 s, scrapes visible creator/video data, and uploads raw
  observations. **No** scoring/tagging/recommendation logic lives here.
* **Backend** receives observations, normalizes + dedupes them, runs
  scoring/tagging/recommendation rules, opens manual-review tasks, and
  exports CSVs. Also serves the operator UI at `/ui/`.
* **Desktop app (Electron)** owns the lifecycle: spawns the python
  backend as a child process, polls `/health`, opens a window on
  `http://127.0.0.1:8000/ui/`. The same UI runs in a plain browser if
  you don't want to install Electron.

## Quick start (Windows)

Pre-reqs: Python 3.11 (`py -3.11`), Chrome.

```powershell
cd "F:\AI Agent\Auto boker grab\x9_creator_desktop_system"

# 1. Install python deps
py -3.11 -m pip install -r requirements.txt

# 2. Initialize the database (idempotent)
py -3.11 -m x9_creator_desktop_system.backend.migrations.001_init

# 3. Start backend + open UI in default browser (no Electron needed)
.\start_desktop.bat

# 4. Install the chrome extension
#    Chrome  ->  chrome://extensions  ->  Developer mode  ->
#    Load unpacked  ->  pick chrome-extension/
#    Open TikTok and log in. Heartbeats start automatically.
```

To run the full Electron desktop shell instead:

```powershell
cd "F:\AI Agent\Auto boker grab\x9_creator_desktop_system\desktop"
npm install
npm start
```

## Backend layout

```
backend/
├── main.py                      FastAPI app + /ui static mount
├── config.py                    settings, paths, versions
├── database/connection.py       SQLAlchemy engine + init_db
├── models/                      8 ORM models
├── routers/                     8 router modules
├── services/
│   ├── collector_service.py     observation -> creator upsert
│   ├── scoring_engine.py        pure score computation
│   ├── tag_engine.py            risk + positive tags
│   ├── recommendation_engine.py product/collab/queue/priority decision
│   ├── pipeline.py              full pipeline (score+tag+rec+review)
│   ├── review_task_service.py   manual review lifecycle
│   └── export_service.py        recommended-creators.csv
├── utils/
│   ├── keyword_rules_v3.py      single source of truth for keywords
│   ├── id_utils.py
│   └── json_utils.py            includes parse_followers_count('844.5K')
├── migrations/001_init.py       schema + tag-catalog seed (idempotent)
├── tests/
│   ├── conftest.py              fresh on-disk DB per test session
│   ├── test_acceptance.py       8 spec acceptance tests
│   └── test_unit_scoring.py     7 pure scoring/recommendation tests
└── ui/
    ├── index.html               Dashboard / Collection / Recommendations
    ├── style.css                / Manual Review / Export / Settings
    └── app.js
```

## API endpoints

Health & control

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness probe |
| GET | `/api/local/app/status` | versions, env |
| POST | `/api/local/app/restart` | desktop signal |
| GET | `/api/local/db/status` | db url + ok |
| POST | `/api/local/db/migrate` | re-run migration |
| GET | `/api/local/db/stats` | counts per table |

Extension + collector

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/local/extension/heartbeat` | sent every 5 s by extension |
| GET | `/api/local/extension/status` | online sessions + last heartbeat |
| POST | `/api/local/collector/observations` | raw creator observation |
| GET | `/api/local/collector/recent-observations` | latest uploads |

Processing

| Method | Path |
|---|---|
| POST | `/api/local/process/score-creators` |
| POST | `/api/local/process/tag-creators` |
| POST | `/api/local/process/recommend-creators` |
| POST | `/api/local/process/run-full-pipeline` |

The four process endpoints all run the unified pipeline (score → tag →
recommend → review-task) since v3 keeps them in lockstep. They accept
optional `{"creator_id": "...", "limit": N}` bodies.

Creators

| GET path | Notes |
|---|---|
| `/api/local/creators` | filterable by queue_type, has_email, search_keyword, min/max followers |
| `/api/local/creators/recommended` | recommended/recommended_after_review/low_cost_test/affiliate_test |
| `/api/local/creators/by-tag/{tag_code}` | OR filter by single tag |
| `/api/local/creators/by-queue/{queue_code}` | by queue |
| `/api/local/creators/by-product/{product_type}` | by recommended_product_type |
| `/api/local/creators/by-collab/{collab_type}` | by recommended_collab_type |
| `/api/local/creators/{creator_id}` | detail |

Review tasks + export

| Method | Path |
|---|---|
| GET | `/api/local/review-tasks` |
| PATCH | `/api/local/review-tasks/{task_id}` |
| GET | `/api/local/export/recommended-creators.csv` |

## Scoring formula

`recommendation_score` is computed per creator and clamped to `0..100`:

```
recommendation_score =
    primary_product_fit_score * 0.45
  + commercial_value_score    * 0.20
  + content_format_score      * 0.15
  + follower_scale_score      * 0.10
  + data_quality_score        * 0.05
  + audience_fit_bonus        * 0.05
```

* `contactability_score` (0/50/100, derived from email only) is **a
  hard gate**, not a weight. No email ⇒ creator goes straight to
  `no_contact_info_queue`.
* `audience_fit_score` is capped at 10. It can never dominate.
* Follower scale follows the spec: `<10K:20, 10-49K:40, 50-199K:60,
  200-999K:80, ≥1M:90`. But large creators with low product fit are
  routed to `macro_brand_awareness_queue`, not conversion.
* `content_format_status` distinguishes `match`, `partial_match`,
  `not_match`, `unknown`. Unknown only fires when there's literally no
  text at all — having a bio that doesn't mention review/UGC counts as
  `not_match`, not `unknown`.

## The search-keyword-only rule (the most important hard gate)

If `feminine_care_fit` exists ONLY because the search keyword (e.g.
"sanitary pads") matched, but `bio`, `source_video_title` and
`source_video_description` contain no real feminine-care evidence:

* risk tags `search_keyword_only_match` and `manual_review_required`
  are added.
* `review_required = 1`, `review_status = "pending"`,
  `review_reason = "Only matched by search keyword; bio/video evidence
  does not confirm feminine-care relevance. Manual review required."`
* `queue_type = manual_review_queue`,
  `recommendation_status = manual_review_before_outreach`,
  `recommended_collab_type = do_not_contact_now`.
* The creator **never** enters `feminine_conversion_queue` directly —
  an operator has to PATCH the review task to `approved` first.

When the operator approves, blocking risk tags are dropped, the queue
is recalculated and the next pipeline run can promote the creator into
a real outreach queue.

## Queues (9 total)

| Queue | Trigger |
|---|---|
| `feminine_conversion_queue` | `feminine_care_fit ≥ 70`, real evidence, `cv ≥ 50`, has email |
| `feminine_warm_lead_queue` | `40 ≤ fcf ≤ 69`, `data_quality ≥ 70`, `cv ≥ 50` |
| `sample_collab_test_queue` | `followers ≤ 100K`, `cv ≥ 70`, `20 ≤ fit ≤ 59` |
| `affiliate_test_queue` | `cv ≥ 70`, fit `< 60` |
| `macro_brand_awareness_queue` | `followers ≥ 500K`, fit `< 40` |
| `manual_review_queue` | `search_keyword_only_match`, weak evidence, or unknown format |
| `general_lifestyle_hold` | `fit < 40`, no fast verdict |
| `not_recommended_queue` | `fit < 20` AND `cv < 40` |
| `no_contact_info_queue` | no usable email |

Routing is decided by `recommendation_engine.decide()`. Hard gates
(no email, search-keyword-only) are checked first; the macro-low-fit
rule fires before generic weak-evidence routing so big creators with
stale signals don't land in manual review.

## Tag groups

The tagging engine emits multiple tags per creator across:
`risk`, `positive`, `product_category`, `product_fit`,
`content_vertical`, `content_format`, `collaboration`. Tags are stored
in `creator_tags` and (compactly) on the creator row in
`risk_tags_json`/`positive_tags_json`. Filter via `/by-tag/{tag_code}`.

The seven granular feminine SKU buckets (`feminine_care_daily_liner`,
`period_care_pad`, `sensitive_skin_care`, `travel_hygiene_pack`,
`postpartum_mom_care`, `teen_first_period_care`,
`wellness_self_care_bundle`) are picked by signature phrases in
`utils/keyword_rules_v3.py::FEMININE_PRODUCT_BUCKETS`.

## Tests

```powershell
py -3.11 -m pytest x9_creator_desktop_system/backend/tests -v
```

14 tests in two files:

`test_acceptance.py` (8) — health, migration idempotent, heartbeat,
observation ingest, search_keyword_only_match end-to-end, multi-queue
recommendation routing, manual-review approval flow, CSV export with
required fields.

`test_unit_scoring.py` (7) — pure rule-engine tests for the search-only
gate, strong-evidence path, no-email gate, macro-low-fit path,
audience cap, contactability email-only.

## Data flow

```
1. Extension popup -> save worker_id / account_id
2. Extension service worker -> POST /heartbeat every 5 s
3. Content script on TikTok -> scrape visible profile/video text
4. Service worker -> POST /collector/observations
5. Backend.collector_service -> raw_observations + upsert creators
6. (manual or scheduled) POST /process/run-full-pipeline
7. Backend.pipeline -> score, tag, recommend, open review tasks
8. Operator opens /ui/ -> reviews dashboard, approves tasks
9. Operator clicks Export -> recommended-creators.csv
```

## Compliance

The extension only reads visible page text on tabs the operator
navigated to manually. It does **not** auto-like, auto-comment,
auto-follow, auto-message, or repost; it does not bypass login or
CAPTCHA; it does not read private data. This version is for
collection, recommendation, review and export only.

## Sample output

A representative run on six seed creators produces this routing:

| Creator | Followers | Queue | Product type | Collab type | Priority |
|---|---:|---|---|---|---|
| natashathasan | 844,500 | feminine_conversion_queue | feminine_care_daily_liner | paid_test_collab | P2 |
| paulinejchoii | 120,000 | feminine_warm_lead_queue | wellness_self_care_bundle | sample_collab | P2 |
| jasminechiswell | 18,800,000 | macro_brand_awareness_queue | — | brand_awareness_collab | P4 |
| dainty.nugs | 38,700 | manual_review_queue | — | do_not_contact_now | P4 |
| hellokittygrisel | 10,100 | manual_review_queue | — | do_not_contact_now | P4 |
| quiet.creator | 20,000 | no_contact_info_queue | — | do_not_contact_now | P4 |

Sample CSV at `data/exports/recommended-creators.csv` after a pipeline
run.
