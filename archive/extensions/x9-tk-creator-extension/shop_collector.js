/* TikTok Shop creator collector (v6).
 * v6: click handle text (not avatar). Avatar has no own click handler on
 *     TikTok Shop, so clicking it doesn't navigate — that caused the
 *     `detail_tab_did_not_open` timeouts in v5. Handle span has the
 *     navigation handler; duplicate tabs from one click are cleaned up
 *     by shop_runner.
 */
(() => {
  if (window.__TSCLB_SHOP_COLLECTOR__) return;
  window.__TSCLB_SHOP_COLLECTOR__ = true;

  const TAG = "[TSCLB-CS]";
  const MSG = {
    AUTO_FULL_RUN: "TSCLB_AUTO_FULL_RUN", AUTO_STOP: "TSCLB_AUTO_STOP",
    CLICK_ROW: "TSCLB_CLICK_ROW", SCAN_DETAIL_NOW: "TSCLB_SCAN_DETAIL_NOW",
    PROBE_PAGE: "TSCLB_PROBE_PAGE",
    LIST_BATCH: "TSCLB_LIST_BATCH", LIST_DONE: "TSCLB_LIST_DONE",
    AUTO_RUN_FINISHED: "TSCLB_AUTO_RUN_FINISHED",
    ERROR: "TSCLB_CS_ERROR", PROGRESS: "TSCLB_PROGRESS",
  };
  const HOST_AFFILIATE = /(^|\.)affiliate-us\.tiktok\.com$/i;
  const HOST_SELLER = /(^|\.)seller-us\.tiktok\.com$/i;
  const LIST_PATH = /\/connection\/creator(?:\/?$|\/?\?)/i;
  const DETAIL_PATH = /\/connection\/creator\/detail/i;
  const SECTION_NAMES = [
    "Sales", "Video", "LIVE", "Followers", "Trends", "Rating", "Audience",
    "Example videos", "All videos", "Top brands", "Brand collaborations",
    "Similar creators", "Creators with similar content",
    "GMV by product category", "GMV per sales channel", "GMV per customer",
    "Categories", "Content quality", "Collaboration metrics",
  ];

  let listRunning = false; let listAbort = false;

  console.log(TAG, "loaded on", location.href, "page_type=", detectPageType());

  chrome.runtime.onMessage.addListener((msg, _s, send) => {
    console.log(TAG, "msg in:", msg && msg.type);
    handle(msg)
      .then((p) => send({ ok: true, ...(p || {}) }))
      .catch((e) => { console.warn(TAG, "msg err:", e); send({ ok: false, error: String(e && e.message || e) }); });
    return true;
  });

  try {
    chrome.storage && chrome.storage.local && chrome.storage.local.get(["shopAutoRun"], (got) => {
      const run = got && got.shopAutoRun;
      if (!run || run.status !== "running") return;
      if (detectPageType() === "creator_list" && !listRunning) {
        const tc = (run.settings && run.settings.taskCount) || 9999;
        console.log(TAG, "auto-resume list taskCount=" + tc);
        queueMicrotask(() => runListPhase(tc).catch(reportError));
      }
    });
  } catch (_) {}

  async function handle(message) {
    message = message || {};
    switch (message.type) {
      case MSG.AUTO_FULL_RUN: return startList(message);
      case MSG.AUTO_STOP: { listAbort = true; listRunning = false; return { stopped: true }; }
      case MSG.CLICK_ROW: return doClickRow(message);
      case MSG.SCAN_DETAIL_NOW: return doScanDetail(message);
      case MSG.PROBE_PAGE: return { page_type: detectPageType(), url: location.href };
      default: return null;
    }
  }

  function startList(opts) {
    const pt = detectPageType();
    if (pt !== "creator_list") return { ok: false, error: "not_on_list_page", page_type: pt };
    if (listRunning) return { ok: false, error: "already_running" };
    const taskCount = Math.max(1, parseInt(opts && opts.taskCount, 10) || 9999);
    runListPhase(taskCount).catch(reportError);
    return { ok: true, started: true, taskCount };
  }

  async function runListPhase(taskCount) {
    if (listRunning) return;
    listRunning = true; listAbort = false;
    taskCount = taskCount || 9999;
    console.log(TAG, "list phase START taskCount=" + taskCount);

    try {
      const seen = new Set(); const handles = [];
      const scroller = findScrollContainer();
      const maxIter = 80; const noNewLimit = 4;

      const firstFresh = [];
      for (const it of collectCreatorList()) {
        if (handles.length >= taskCount) break;
        if (it.handle && !seen.has(it.handle)) { seen.add(it.handle); handles.push(it.handle); firstFresh.push(it); }
      }
      console.log(TAG, "initial sweep:", firstFresh.length, "/", taskCount);
      if (firstFresh.length) send(MSG.LIST_BATCH, { items: firstFresh, source_page_url: location.href });
      progress({ phase: "list_scanning", listSeen: handles.length });

      let noNew = 0;
      for (let i = 0; i < maxIter && !listAbort && handles.length < taskCount; i += 1) {
        scrollElement(scroller);
        await sleep(950 + Math.floor(Math.random() * 400));

        const fresh = [];
        for (const it of collectCreatorList()) {
          if (handles.length >= taskCount) break;
          if (it.handle && !seen.has(it.handle)) { seen.add(it.handle); handles.push(it.handle); fresh.push(it); }
        }
        if (fresh.length) {
          console.log(TAG, "iter", i, "fresh=", fresh.length, "total=" + handles.length + "/" + taskCount);
          send(MSG.LIST_BATCH, { items: fresh, source_page_url: location.href });
          progress({ phase: "list_scanning", listSeen: handles.length });
          noNew = 0;
        } else { noNew += 1; }
        if (noNew >= noNewLimit) break;
        if (handles.length >= taskCount) break;
        const lower = visibleText(document.body).slice(0, 8000).toLowerCase();
        if (/no more|end of results|no creators|no data/.test(lower)) break;
      }

      await scrollToTop(scroller);
      console.log(TAG, "list DONE total=" + handles.length);
      send(MSG.LIST_DONE, { handles, source_page_url: location.href });
    } finally { listRunning = false; }
  }

  async function doClickRow(opts) {
    const handle = opts && opts.handle;
    if (detectPageType() !== "creator_list") return { ok: false, error: "not_on_list_page" };
    const row = await findRowByHandle(handle);
    if (!row) { console.warn(TAG, "row not found @" + handle); return { ok: false, error: "row_not_found" }; }
    const target = pickClickTarget(row);
    console.log(TAG, "click @" + handle, "via", target.tagName, target.className);
    try { target.scrollIntoView({ block: "center", behavior: "auto" }); } catch (_) {}
    await sleep(150);
    try { target.click(); } catch (e) { return { ok: false, error: "click_threw:" + String(e && e.message || e) }; }
    return { ok: true, clicked: handle };
  }

  function pickClickTarget(row) {
    // v6: prefer the handle text span — TikTok Shop's onClick handler lives
    // there. Avatar has no handler and clicking it does nothing.
    const handleSpan = row.querySelector("span.text-body-m-medium");
    if (handleSpan && isVisible(handleSpan)) return handleSpan;
    const displaySpan = row.querySelector("span.text-overflow-single");
    if (displaySpan && isVisible(displaySpan)) return displaySpan;
    const firstCell = row.querySelector(".arco-table-td:not(.arco-table-checkbox)");
    if (firstCell && isVisible(firstCell)) return firstCell;
    return row;
  }

  async function findRowByHandle(handle) {
    const lc = String(handle || "").toLowerCase();
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const rows = listRowElements();
      for (const row of rows) {
        const candidates = row.querySelectorAll("span.text-body-m-medium, span.text-overflow-single");
        for (const c of candidates) {
          const t = (c.textContent || "").trim().toLowerCase();
          if (t === lc) return row;
        }
      }
      scrollElement(findScrollContainer());
      await sleep(700);
    }
    return null;
  }

  async function doScanDetail(_opts) {
    console.log(TAG, "doScanDetail start", location.href);
    const t0 = Date.now(); let heading = null;
    while (Date.now() - t0 < 12000) {
      heading = document.querySelector("span.text-head-l");
      if (heading) {
        const txt = (heading.textContent || "").trim();
        if (txt && /^[a-z0-9._-]{2,40}$/i.test(txt)) break;
      }
      await sleep(300);
    }
    if (!heading) { console.warn(TAG, "no handle heading after 12s"); return { ok: false, error: "detail_handle_not_found", url: location.href }; }
    console.log(TAG, "handle heading=" + (heading.textContent || "").trim());
    await sleep(800);
    const observation = buildDetailObservation();
    console.log(TAG, "scraped handle=" + (observation && observation.creator && observation.creator.handle));
    return { ok: true, observation, source_page_url: location.href };
  }

  async function scrollToTop(el) {
    try { el.scrollTo({ top: 0, behavior: "auto" }); } catch (_) { el.scrollTop = 0; }
    await sleep(400);
  }

  function detectPageType() {
    const host = location.hostname.toLowerCase();
    if (!HOST_AFFILIATE.test(host) && !HOST_SELLER.test(host)) return "other";
    if (DETAIL_PATH.test(location.pathname)) return "creator_detail";
    if (LIST_PATH.test(location.pathname)) {
      const rows = listRowElements();
      if (rows.length >= 1) return "creator_list";
    }
    return "other";
  }

  function listRowElements() {
    const rows = Array.from(document.querySelectorAll(".arco-table-tr, tr[role='row'], tr"));
    return rows.filter((row) => {
      const text = visibleText(row);
      if (text.length < 20 || text.length > 6000) return false;
      return !!row.querySelector(".text-body-m-medium, span.text-overflow-single");
    }).slice(0, 400);
  }

  function collectCreatorList() {
    const rows = listRowElements();
    const out = []; const seen = new Set();
    rows.forEach((row, idx) => {
      const item = parseListRow(row, idx);
      if (!item || !item.handle || seen.has(item.handle)) return;
      seen.add(item.handle); out.push(item);
    });
    return out;
  }

  function parseListRow(row, idx) {
    const text = visibleText(row);
    const lines = textLines(text);
    const handle = findHandle(row, lines);
    if (!handle) return null;
    return {
      handle, display_name: findDisplayName(row, lines, handle),
      profile_url: `https://www.tiktok.com/@${handle}`, shop_profile_url: null,
      avatar_url: findAvatarUrl(row), followers_raw: findFollowersRaw(text),
      followers_count: null,
      gmv_raw: findNearestMetricRaw(text, "GMV") || findCurrency(text),
      gpm_raw: findNearestMetricRaw(text, "GPM"),
      avg_commission_rate_raw: findNearestMetricRaw(text, "commission") || findPercent(text),
      category_text: findCategoryText(lines),
      invite_status: findStatus(text, ["Invite", "Invited", "Previously invited"]),
      save_status: findStatus(text, ["Saved", "Save"]),
      row_index: idx + 1,
      card_visible_text: trimTo(text, 5000),
      card_html: trimTo(row.outerHTML || "", 40000),
      card_json: { tag: row.tagName, class_name: row.className || "" },
      source_page_url: location.href,
      collected_at: new Date().toISOString(),
    };
  }

  function findHandle(row, lines) {
    const candidates = Array.from(row.querySelectorAll(
      "span.text-body-m-medium, span.text-overflow-single, span.text-head-l"
    ));
    for (const el of candidates) {
      const text = (el.textContent || "").trim();
      if (/^[a-z0-9._-]{2,40}$/i.test(text) && /[a-z]/i.test(text)) return text.toLowerCase();
    }
    for (const line of lines) {
      if (/^[a-z0-9._-]{3,40}$/i.test(line) && /[a-z]/i.test(line)) return line.toLowerCase();
    }
    return null;
  }

  function findDisplayName(row, lines, handle) {
    const lc = (handle || "").toLowerCase();
    return lines.find((l) =>
      l && l.toLowerCase() !== lc && !/^\$|\bGMV\b|\bGPM\b|^PPS\b|^\d/i.test(l)
      && l.length >= 2 && l.length <= 160
    ) || lc || null;
  }

  function buildDetailObservation() {
    const rawDomHtml = trimTo((document.documentElement && document.documentElement.outerHTML) || "", 1500000);
    const fullVisibleText = visibleText(document.body);
    const identityText = truncateAtSimilarSection(fullVisibleText);
    const handle = detailHandle();
    const displayName = detailDisplayName(handle) || handle || document.title;
    return {
      event_type: "creator_observation", platform: "tiktok_shop",
      creator: {
        handle, display_name: displayName,
        profile_url: handle ? `https://www.tiktok.com/@${handle}` : null,
        shop_profile_url: location.href,
        avatar_url: findAvatarUrl(document),
        followers_raw: findFollowersRaw(identityText), followers_count: null,
      },
      tiktok_shop: {
        source_page_url: location.href,
        raw_capture: {
          page_title: document.title || null,
          page_type: "creator_detail",
          captured_at: new Date().toISOString(),
          links: collectRawLinks(),
        },
        raw_visible_text: trimTo(fullVisibleText, 300000),
        raw_dom_html: rawDomHtml,
      },
      lead_status: "shop_profile_collected",
      collected_at: new Date().toISOString(),
    };
  }

  function collectRawLinks() {
    return uniqueStrings(Array.from(document.querySelectorAll("a[href]"))
      .map((a) => absolutize(a.getAttribute("href") || ""))
      .filter(Boolean)).slice(0, 300);
  }

  function truncateAtSimilarSection(text) {
    const t = String(text || "");
    const cands = ["Creators with similar content", "Similar creators"];
    let cut = -1;
    for (const c of cands) {
      const i = t.indexOf(c);
      if (i >= 0 && (cut < 0 || i < cut)) cut = i;
    }
    return cut > 0 ? t.slice(0, cut) : t;
  }
  function inSimilarSection(el) {
    let cur = el;
    while (cur && cur !== document.body) {
      if (cur.id === "similar_creator") return true;
      if (cur.previousElementSibling && cur.previousElementSibling.id === "similar_creator") return true;
      cur = cur.parentElement;
    }
    return false;
  }

  function detailHandle() {
    const heading = document.querySelector("span.text-head-l");
    if (heading) {
      const t = (heading.textContent || "").trim();
      if (/^[a-z0-9._-]{2,40}$/i.test(t)) return t.toLowerCase();
    }
    const title = (document.title || "").trim();
    const tm = title.match(/^([a-z0-9._-]{2,40})\s*\|/i);
    if (tm) return tm[1].toLowerCase();
    return null;
  }

  function detailDisplayName(handle) {
    const lc = (handle || "").toLowerCase();
    const nodes = document.querySelectorAll("span.leading-21.text-overflow-single, span.text-body-m-regular, span.text-body-s-regular");
    for (const el of nodes) {
      const t = (el.textContent || "").trim();
      if (!t || t.toLowerCase() === lc) continue;
      if (t.length < 2 || t.length > 160) continue;
      if (/^\$|\bGMV\b|\bGPM\b|^\d|^Excellent$|^High$|^Good$|^Strong$|^Female$|^Male$/i.test(t)) continue;
      return t;
    }
    return null;
  }

  function detailProfile(lines, fullText) {
    let bio = null;
    const bioEl = document.querySelector("span.break-words.whitespace-pre-wrap, span.whitespace-pre-wrap");
    if (bioEl) bio = trimTo((bioEl.textContent || "").trim(), 500);

    const categories = [];
    const catEl = document.querySelector("span.text-overflow-single[style*='max-width: 130px']");
    if (catEl) {
      const t = (catEl.textContent || "").trim();
      if (t) categories.push(t);
    }
    const tagPills = Array.from(document.querySelectorAll("span.rounded-10.bg-\\[\\#ECECED\\], span[class*='bg-[#ECECED]']"));
    const tags = tagPills.map((el) => (el.textContent || "").trim()).filter(Boolean);

    return {
      categories: uniqueStrings(categories.concat(tags.filter((t) => /beauty|personal care|skincare|fashion|home|kitchen|household|health|baby|pet|food|sports|fitness|tech|electronics|lifestyle|appliances/i.test(t)))).slice(0, 8),
      primary_category: categories[0] || null,
      mcn_name: findLabelValue("MCN") || findLabelValue("Creator agency") || null,
      flat_fee_eligible: /eligible for flat fee/i.test(fullText) || tags.some((t) => /eligible for flat fee/i.test(t)) ? true : null,
      rating_level: findRatingNumber() || findRatingLevel(lines, "Rating") || findRatingLevel(lines, "Content quality"),
      sales_level: findRatingLevel(lines, "Sales"),
      video_level: findRatingLevel(lines, "Video"),
      live_level: findRatingLevel(lines, "LIVE"),
      trends_level: findRatingLevel(lines, "Trends"),
      bio, status_tags: tags,
    };
  }

  function collectMetricsFromCards() {
    const out = []; const seen = new Set();
    const sectionMap = {
      sales_tab: "Sales", collab_history: "Collaboration metrics",
      video_tab: "Video", live_tab: "LIVE", followers_tab: "Followers",
      trends_tab: "Trends", sample_credit_score: "Sample score", pps: "PPS",
    };
    const cardLabels = Array.from(document.querySelectorAll("span.text-body-l-regular.text-overflow-single"));
    for (const labelEl of cardLabels) {
      if (inSimilarSection(labelEl)) continue;
      const label = (labelEl.textContent || "").trim();
      if (!label) continue;
      const card = labelEl.closest(".rounded-10, .rounded-8, .border-1");
      if (!card) continue;
      const valueEl = card.querySelector("span.text-head-l, span.text-head-xl");
      if (!valueEl) continue;
      const value = (valueEl.textContent || "").trim();
      if (!value) continue;
      let section = "Overview"; let cur = card;
      for (let depth = 0; depth < 30 && cur; depth += 1) {
        const prev = cur.previousElementSibling;
        if (prev && prev.id && sectionMap[prev.id]) { section = sectionMap[prev.id]; break; }
        cur = cur.parentElement;
      }
      const key = `${section}|${label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        section_name: section, metric_name: label, metric_value_raw: value,
        metric_unit: /\$/.test(value) ? "USD" : /%/.test(value) ? "percent" : "count",
        date_range: findCardDateRange(card),
      });
    }
    return out.slice(0, 200);
  }

  function findCardDateRange(card) {
    let cur = card;
    for (let depth = 0; depth < 6 && cur; depth += 1) {
      const dr = cur.querySelector && cur.querySelector("span.font-normal.text-neutral-text3, span.text-neutral-text3.text-14");
      if (dr) {
        const t = (dr.textContent || "").trim();
        if (/\d{4}/.test(t)) return t;
      }
      cur = cur.parentElement;
    }
    return null;
  }

  function findLabelValue(label) {
    const labelSpans = Array.from(document.querySelectorAll("span"));
    for (const el of labelSpans) {
      if ((el.textContent || "").trim() !== label) continue;
      let sib = el.nextElementSibling;
      while (sib && (!sib.textContent || !sib.textContent.trim())) sib = sib.nextElementSibling;
      if (sib) {
        const v = (sib.textContent || "").trim();
        if (v && v !== label) return trimTo(v, 200);
      }
    }
    return null;
  }

  function findRatingNumber() {
    const ratingLabel = Array.from(document.querySelectorAll("span")).find((el) =>
      (el.textContent || "").trim() === "Rating" && el.className.includes("w-80")
    );
    if (!ratingLabel) return null;
    const parent = ratingLabel.parentElement; if (!parent) return null;
    const sib = parent.nextElementSibling; if (!sib) return null;
    const num = sib.querySelector("span");
    return num ? (num.textContent || "").trim() : null;
  }

  function collectAudience(lines) {
    const out = [];
    lines.forEach((line) => {
      const p = findPercent(line); if (!p) return;
      if (/female|male/i.test(line)) {
        out.push({ segment_type: "gender", segment_name: line.replace(p, "").trim() || (/female/i.test(line) ? "Female" : "Male"), value_raw: p });
      } else if (/\b\d{2}\s*-\s*\d{2}\b|\b55\+\b|\b65\+\b/.test(line)) {
        out.push({ segment_type: "age", segment_name: line.replace(p, "").trim(), value_raw: p });
      } else if (/united states|usa|canada|mexico|uk|united kingdom|australia/i.test(line)) {
        out.push({ segment_type: "region", segment_name: line.replace(p, "").trim(), value_raw: p });
      }
    });
    return out.slice(0, 120);
  }

  function collectBrands(lines) {
    const start = lines.findIndex((l) => /^(top brands|brand collaborations|partner collabs)$/i.test(l));
    if (start < 0) return [];
    const out = [];
    for (let i = start + 1; i < Math.min(lines.length, start + 80); i += 1) {
      const line = lines[i];
      if (!line) continue;
      if (SECTION_NAMES.some((s) => equalsLoose(line, s)) && !/^(top brands|brand collaborations|partner collabs)$/i.test(line)) break;
      if (line.length < 2 || line.length > 80 || findMetricValue(line)) continue;
      out.push({ rank: out.length + 1, brand_name: line });
      if (out.length >= 30) break;
    }
    return out;
  }

  function collectVideos() {
    const captions = Array.from(document.querySelectorAll(".text-body-m-medium.text-overflow-muli-2"));
    const out = []; const seen = new Set();
    for (const cap of captions) {
      if (inSimilarSection(cap)) continue;
      const text = trimTo((cap.textContent || "").trim(), 600);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      const card = cap.closest("div"); let release = "";
      if (card) {
        const t = card.querySelector(".text-12.leading-18.text-neutral-text3, .text-neutral-text3");
        if (t) release = (t.textContent || "").trim();
      }
      out.push({ video_url: "", title: text, release_time: release });
      if (out.length >= 30) break;
    }
    return out;
  }

  function collectSections(text) {
    const out = {};
    SECTION_NAMES.forEach((name) => {
      const idx = text.toLowerCase().indexOf(name.toLowerCase());
      if (idx >= 0) out[name] = { visible_text: trimTo(text.slice(idx, idx + 3500), 3500) };
    });
    return out;
  }

  function findLocationLine(lines) {
    return (lines || []).find((l) => /📍|🇺🇸|🇨🇦|🇲🇽|AZ|CA|NY|TX|FL|USA|United States/i.test(l) && l.length <= 120) || null;
  }

  function send(type, payload) {
    try { chrome.runtime.sendMessage({ type, ...payload }, () => void chrome.runtime.lastError); } catch (_) {}
  }
  function progress(payload) { send(MSG.PROGRESS, payload); }
  function reportError(err) { console.error(TAG, err); send(MSG.ERROR, { phase: "exception", message: String(err && err.message || err) }); }

  function visibleText(root) {
    if (!root) return "";
    const text = root.innerText || root.textContent || "";
    return text.replace(/ /g, " ").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  function textLines(text) {
    return String(text || "").split(/\n+/).map((l) => l.replace(/\s+/g, " ").trim()).filter(Boolean);
  }
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
  function trimTo(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n) : s; }
  function absolutize(u) { try { return new URL(u, location.href).href; } catch { return null; } }
  function equalsLoose(a, b) { return String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase(); }
  function uniqueStrings(items) {
    const seen = new Set(); const out = [];
    for (const x of items) { const s = String(x || "").trim(); if (!s || seen.has(s)) continue; seen.add(s); out.push(s); }
    return out;
  }
  function isVisible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  }
  function findScrollContainer() {
    const all = Array.from(document.querySelectorAll("body *")).filter((el) => {
      const s = getComputedStyle(el);
      return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 200;
    }).sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
    return all[0] || document.scrollingElement || document.documentElement;
  }
  function scrollElement(el) {
    const delta = Math.max(480, Math.floor((el.clientHeight || window.innerHeight) * 0.8));
    el.scrollBy({ top: delta, left: 0, behavior: "smooth" });
  }
  function findAvatarUrl(root) {
    const img = Array.from((root.querySelectorAll && root.querySelectorAll("img")) || []).find((i) => i.src && !/^data:/i.test(i.src));
    return img ? absolutize(img.src) : null;
  }
  function findFollowersRaw(text) {
    const m = String(text || "").match(/([\d,.]+)\s*([KMB])?\s*(followers?|fans)\b/i);
    if (m) return `${m[1]}${m[2] || ""}`;
    const cm = String(text || "").match(/\b([\d,.]+\s*[KMB])\b/i);
    return cm ? cm[1].replace(/\s+/g, "") : null;
  }
  function findNearestMetricRaw(text, label) {
    const e = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const r = new RegExp(`${e}.{0,40}(\\$?\\d[\\d,.]*\\s*[KMB]?%?)`, "i");
    const m = String(text || "").match(r);
    return m ? m[1].replace(/\s+/g, "") : null;
  }
  function findMetricValue(line) {
    const t = String(line || "");
    const c = t.match(/\$[\d,.]+\s*[KMB]?/i);
    if (c) return { raw: c[0].replace(/\s+/g, ""), unit: "USD" };
    const p = t.match(/\b\d+(?:\.\d+)?\s*%/);
    if (p) return { raw: p[0].replace(/\s+/g, ""), unit: "percent" };
    const k = t.match(/\b\d+(?:\.\d+)?\s*[KMB]\b/i);
    if (k) return { raw: k[0].replace(/\s+/g, ""), unit: "count" };
    return null;
  }
  function findCurrency(text) { const m = String(text || "").match(/\$[\d,.]+\s*[KMB]?/i); return m ? m[0].replace(/\s+/g, "") : null; }
  function findPercent(text) { const m = String(text || "").match(/\b\d+(?:\.\d+)?\s*%/); return m ? m[0].replace(/\s+/g, "") : null; }
  function findStatus(text, ss) { const f = ss.find((s) => new RegExp(`\\b${s}\\b`, "i").test(text)); return f || null; }
  function findCategoryText(lines) {
    return lines.find((l) => /\b(beauty|personal care|skincare|fashion|home|kitchen|household|health|baby|pet|food|sports|fitness|tech|electronics|lifestyle|appliances)\b/i.test(l)) || null;
  }
  function findRatingLevel(lines, label) {
    const i = lines.findIndex((l) => equalsLoose(l, label));
    if (i < 0) return null;
    const candidates = lines.slice(i + 1, i + 5);
    for (const c of candidates) {
      if (/^(excellent|high|good|new|up|down|strong|weak|average|medium|not yet rated)$/i.test(c)) return c;
    }
    return null;
  }

  try {
    window.__TSCLB_TEST_HOOKS__ = { buildDetailObservation };
  } catch (_) {}
})();
