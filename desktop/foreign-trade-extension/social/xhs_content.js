(() => {
  if (window.__XHS_CREATOR_COLLECTOR__) return;
  window.__XHS_CREATOR_COLLECTOR__ = true;

  const TAG = "[XHS-CS]";
  const MSG = {
    CS_START: "XHS_CS_START",
    CS_STOP: "XHS_CS_STOP",
    PROGRESS: "XHS_PROGRESS",
    NOTE_DONE: "XHS_NOTE_DONE",
    DONE: "XHS_DONE",
    ERROR: "XHS_ERROR",
    EXPECT_PROFILE: "XHS_EXPECT_PROFILE",
    WAIT_PROFILE: "XHS_WAIT_PROFILE",
    PROFILE_RESULT: "XHS_PROFILE_RESULT"
  };

  let running = false;
  let stopped = false;
  let runStartedAt = 0;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || typeof message.type !== "string") return false;
    if (message.type === "XHS_PING") {
      sendResponse({ ok: true, href: location.href });
      return true;
    }
    if (message.type === MSG.CS_STOP) {
      stopped = true;
      running = false;
      sendResponse({ ok: true });
      return true;
    }
    if (message.type === MSG.CS_START) {
      startRun(message.settings || {}, message.runId || "")
        .then((result) => sendResponse({ ok: true, result }))
        .catch((error) => {
          reportError(error);
          sendResponse({ ok: false, error: errText(error) });
        });
      return true;
    }
    return false;
  });

  if (/\/user\/profile\//i.test(location.pathname)) {
    setTimeout(() => collectCurrentProfile().catch((e) => console.warn(TAG, "profile auto collect failed", e)), 1800);
  }

  async function startRun(settings, runId) {
    if (running) return { alreadyRunning: true };
    running = true;
    stopped = false;
    runStartedAt = Date.now();
    const opts = normalizeSettings(settings);
    opts.keyword = detectSearchKeyword() || opts.keyword;
    try {
      await progress("notes", "严格流程：从当前人工结果页开始");
      await ensureManualResultPage();
      await progress("notes", `自动滚动加载当前结果页，目标 ${opts.maxNotes} 篇`);
      const cards = await collectSearchCards(opts.maxNotes);
      if (!cards.length) throw new Error("当前页面没有可采集的笔记卡片。请先人工打开并加载目标结果页。");
      await progress("notes", `已锁定当前页面卡片快照：${cards.length} 篇`);

      const profileSeen = new Set();
      for (let i = 0; i < cards.length && !stopped; i += 1) {
        const card = cards[i];
        await progress("notes", `严格流程 ${i + 1}/${cards.length}：打开笔记 ${card.title || card.note_id}`);
        await openNoteCard(card);
        await waitForNoteReady();
        await progress("notes", `采集帖子图文内容：${card.title || card.note_id}`);
        const note = collectNoteDetail(card, opts.keyword, runId);
        const authorUsers = collectUsersFromNote(note, [], opts.keyword);
        await sendRuntime({ type: MSG.NOTE_DONE, note, comments: [], users: authorUsers });

        let profileCount = countCollectedProfiles(profileSeen);
        if (note.author && (note.author.profile_url || note.author.username)) {
          const key = userKey(note.author);
          if (key && !profileSeen.has(key) && profileCount < opts.profileLimit) {
            await progress("profiles", "新标签页打开帖子作者主页");
            profileSeen.add(key);
            const ok = await openProfileInNewTab(note.author, note, opts.historyLimit, "post_author");
            if (ok) profileCount += 1;
          }
        }

        await progress("comments", "开始采集评论区评论");
        profileCount = await processCommentsStepByStep(note, opts, profileSeen, profileCount);
        await progress("notes", "关闭当前笔记详情，回到原结果页");
        await closeNoteDetail();
        await ensureManualResultPage();
        await sleep(700);
      }

      running = false;
      await sendRuntime({ type: MSG.DONE, message: stopped ? "已停止" : "采集完成" });
      return { ok: true, stopped };
    } catch (error) {
      running = false;
      throw error;
    }
  }

  async function ensureManualResultPage() {
    await waitFor(
      () => document.querySelector(".feeds-container section.note-item, section.note-item"),
      8000,
      "当前页面没有笔记列表。请先人工打开并加载小红书结果页，再点开始。"
    );
  }

  async function collectSearchCards(maxNotes) {
    const cards = new Map();
    let stable = 0;
    let lastCount = 0;
    const scroller = getSearchResultScroller();

    for (let round = 0; round < 40 && cards.size < maxNotes && stable < 6 && !stopped; round += 1) {
      collectSearchCardsFromDom(cards, maxNotes);
      if (cards.size !== lastCount) {
        await progress("notes", `已加载搜索结果卡片 ${cards.size}/${maxNotes}`);
        stable = 0;
        lastCount = cards.size;
      } else {
        stable += 1;
      }
      if (cards.size >= maxNotes || stable >= 6) break;
      scrollSearchResult(scroller, 1050);
      await sleep(850);
    }

    collectSearchCardsFromDom(cards, maxNotes);
    scrollSearchResult(scroller, -1000000);
    await sleep(600);
    return Array.from(cards.values()).slice(0, maxNotes);
  }

  function collectSearchCardsFromDom(cards, maxNotes) {
    const sourceCards = Array.from(document.querySelectorAll(".feeds-container section.note-item, section.note-item"));
    for (const [sourceIndex, card] of sourceCards.entries()) {
      if (card.querySelector(".query-note-wrapper")) continue;
      const link = pickNoteLink(card);
      if (!link) continue;
      const url = absUrl(link.getAttribute("href") || "");
      const noteId = extractNoteId(url);
      const key = noteId || url;
      if (!key || cards.has(key)) continue;
      const author = card.querySelector('a.author[href*="/user/profile/"], a[href*="/user/profile/"]');
      cards.set(key, {
        note_id: noteId,
        source_index: sourceIndex,
        title: text(card.querySelector("a.title") || card.querySelector(".title")),
        note_url: url,
        cover_url: (card.querySelector("a.cover img[src], img[src]") || {}).src || "",
        author_username: text(card.querySelector(".card-bottom-wrapper .name") || card.querySelector(".author .name")),
        author_profile_url: absUrl(author && author.getAttribute("href")),
        like_count_text: text(card.querySelector(".like-wrapper .count")),
        published_at_text: text(card.querySelector(".time")),
        collected_at: new Date().toISOString()
      });
      if (cards.size >= maxNotes) break;
    }
  }

  function getSearchResultScroller() {
    const candidates = [
      document.querySelector(".search-layout__main"),
      document.querySelector(".feeds-container"),
      document.scrollingElement,
      document.body
    ].filter(Boolean);
    return candidates.find((node) => node.scrollHeight > node.clientHeight + 80) || document.scrollingElement || document.body;
  }

  function scrollSearchResult(scroller, delta) {
    if (!scroller || scroller === document.scrollingElement || scroller === document.body || scroller === document.documentElement) {
      if (delta < 0) window.scrollTo(0, 0);
      else window.scrollBy(0, delta);
      return;
    }
    if (delta < 0) scroller.scrollTop = 0;
    else scroller.scrollTop += delta;
  }

  async function openNoteCard(card) {
    const noteId = card.note_id || extractNoteId(card.note_url);
    const target = findNoteClickTarget(noteId);
    if (!target) throw new Error("严格流程停止：当前已加载页面中没有找到可点击笔记：" + noteId);
    target.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(200);
    simulateClick(target);
    await waitFor(() => document.querySelector("#noteContainer, #detail-title, #detail-desc"), 15000, "点击后没有进入笔记详情");
    await sleep(1200);
  }

  async function waitForNoteReady() {
    await waitFor(() => {
      const root = document.querySelector("#noteContainer") || document.querySelector(".note-container");
      if (!root) return false;
      const hasText = Boolean(text(root.querySelector("#detail-title")) || text(root.querySelector("#detail-desc")));
      const hasMedia = Boolean(root.querySelector(".media-container img[src], .swiper-slide img[src], img[data-xhs-img][src]"));
      return hasText || hasMedia;
    }, 12000, "note detail did not become readable");
    await sleep(650);
  }

  function collectNoteDetail(card, keyword, runId) {
    const root = document.querySelector("#noteContainer") || document;
    const authorAnchor = root.querySelector('.author-wrapper a[href*="/user/profile/"], .author-container a[href*="/user/profile/"], a.name[href*="/user/profile/"]');
    const authorName = text(root.querySelector(".author-wrapper .username") || root.querySelector(".author-container .username") || root.querySelector("a.name"));
    const images = unique(Array.from(root.querySelectorAll(".media-container img[src], .swiper-slide img[src], img[data-xhs-img][src]")).map((img) => img.src).filter((src) => src && !src.startsWith("data:")));
    const noteId = extractNoteId(location.href) || card.note_id;
    const note = {
      keyword,
      run_id: runId,
      note_id: noteId,
      title: text(root.querySelector("#detail-title")) || card.title || "",
      desc: text(root.querySelector("#detail-desc")) || "",
      image_urls: images.length ? images : (card.cover_url ? [card.cover_url] : []),
      cover_url: card.cover_url || images[0] || "",
      url: location.href,
      search_result_url: card.note_url || "",
      published_at_text: text(root.querySelector(".bottom-container .date, .date")),
      like_count_text: text(root.querySelector(".engage-bar .like-wrapper .count, .interactions .like-wrapper .count")) || card.like_count_text || "",
      author: {
        username: authorName || card.author_username || "",
        profile_url: absUrl(authorAnchor && authorAnchor.getAttribute("href")) || card.author_profile_url || "",
        user_id: extractUserId(absUrl(authorAnchor && authorAnchor.getAttribute("href")) || card.author_profile_url || ""),
        avatar_url: (root.querySelector(".author-wrapper img[src], .author-container img[src]") || {}).src || card.author_avatar_url || ""
      },
      collected_at: new Date().toISOString()
    };
    return note;
  }

  async function processCommentsStepByStep(note, opts, profileSeen, profileCount) {
    const scroller = document.querySelector(".note-scroller") || document.querySelector(".comments-container") || document.querySelector(".interaction-container") || document.scrollingElement || document.body;
    let stable = 0;
    const seenComments = new Set();
    for (let round = 0; round < 40 && stable < 6 && !stopped; round += 1) {
      clickCommentExpanders();
      await sleep(350);
      const comments = collectComments(note).filter((comment) => {
        if (!comment.comment_id || seenComments.has(comment.comment_id)) return false;
        seenComments.add(comment.comment_id);
        return true;
      });

      if (!comments.length) {
        stable += 1;
      } else {
        stable = 0;
        await progress("comments", `发现新评论 ${comments.length} 条，逐条打开评论者主页`);
        for (const [index, comment] of comments.entries()) {
          if (stopped) break;
          const users = collectUsersFromNote(note, [comment], opts.keyword).filter((user) => user.sources && user.sources.some((s) => s.source_type === "comment"));
          await sendRuntime({ type: MSG.NOTE_DONE, comments: [comment], users });
          const user = users[0] || comment.user;
          if (!user || !user.profile_url) continue;
          if (opts.profileLimit > 0 && profileCount >= opts.profileLimit) continue;
          const key = userKey(user);
          if (!key || profileSeen.has(key)) continue;
          profileSeen.add(key);
          await progress("profiles", `comment ${index + 1}/${comments.length}: open profile ${user.username || key}`);
          await progress("profiles", `新标签页打开评论者主页：${user.username || key}`);
          const ok = await openProfileInNewTab(user, note, opts.historyLimit, "comment", comment);
          if (ok) profileCount += 1;
          await sleep(300);
        }
      }

      if (text(document.querySelector(".end-container")).includes("THE END")) break;
      await progress("comments", "下滑加载新评论");
      if (scroller === document.scrollingElement || scroller === document.body) window.scrollBy(0, 560);
      else scroller.scrollTop = scroller.scrollTop + 900;
      await sleep(800);
    }
    return profileCount;
  }

  function clickCommentExpanders() {
    const re = /展开|查看更多|更多回复|查看.*回复|全部回复/;
    const scope = document.querySelector(".comments-container") || document.querySelector(".note-scroller") || document.querySelector("#noteContainer") || document;
    for (const el of Array.from(scope.querySelectorAll("button, div, span, a")).slice(0, 1200)) {
      const value = text(el);
      if (!value || value.length > 40 || !re.test(value) || !isVisible(el)) continue;
      try { simulateClick(el); } catch (_) {}
    }
  }

  function collectComments(note) {
    const rows = [];
    for (const item of Array.from(document.querySelectorAll('div[id^="comment-"].comment-item'))) {
      const id = item.id || "";
      const depth = item.classList.contains("comment-item-sub") || !!item.closest(".reply-container") ? 1 : 0;
      const parent = item.closest(".parent-comment");
      const rootItem = parent && parent.querySelector(':scope > div[id^="comment-"].comment-item');
      const author = item.querySelector('.author a.name[href*="/user/profile/"], a.name[href*="/user/profile/"]');
      const avatar = item.querySelector(".avatar img[src]");
      const dateBox = item.querySelector(".info .date");
      rows.push({
        comment_id: id.replace(/^comment-/, ""),
        root_comment_id: depth ? ((rootItem && rootItem.id || "").replace(/^comment-/, "")) : id.replace(/^comment-/, ""),
        parent_comment_id: depth ? ((rootItem && rootItem.id || "").replace(/^comment-/, "")) : "",
        depth,
        content: text(item.querySelector(".content .note-text") || item.querySelector(".content")),
        published_at_text: text(dateBox && dateBox.querySelector("span")),
        location: text(dateBox && dateBox.querySelector(".location")),
        like_count_text: text(item.querySelector(".interactions .like .count, .like-wrapper .count")),
        note_id: note.note_id,
        note_title: note.title,
        note_url: note.url,
        note_images: note.image_urls,
        user: {
          username: text(author),
          profile_url: absUrl(author && author.getAttribute("href")),
          user_id: extractUserId(absUrl(author && author.getAttribute("href"))),
          avatar_url: avatar ? avatar.src : ""
        },
        collected_at: new Date().toISOString()
      });
    }
    return rows.filter((row) => row.comment_id && (row.content || row.user.username));
  }

  function collectUsersFromNote(note, comments, keyword) {
    const out = [];
    addUser(out, note.author, {
      source_type: "post_author",
      keyword,
      note_id: note.note_id,
      note_title: note.title,
      note_url: note.url,
      note_images: note.image_urls
    });
    for (const comment of comments) {
      addUser(out, comment.user, {
        source_type: "comment",
        keyword,
        note_id: note.note_id,
        note_title: note.title,
        note_url: note.url,
        note_images: note.image_urls,
        comment_id: comment.comment_id,
        root_comment_id: comment.root_comment_id,
        parent_comment_id: comment.parent_comment_id,
        comment_depth: comment.depth,
        comment_content: comment.content,
        comment_published_at_text: comment.published_at_text,
        comment_location: comment.location
      });
    }
    return out;
  }

  async function openProfileInNewTab(user, note, historyLimit, sourceType, comment) {
    const profileUrl = user.profile_url || "";
    if (!profileUrl) return false;
    const key = userKey(user);
    const link = findProfileAnchor(profileUrl, user.user_id, comment);
    if (!link) return false;
    const requestId = `profile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    await sendRuntime({ type: MSG.EXPECT_PROFILE, requestId, profileUrl, user, sourceType, comment });
    link.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(150);
    const oldTarget = link.getAttribute("target");
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener");
    simulateClick(link);
    if (oldTarget == null) link.removeAttribute("target");
    else link.setAttribute("target", oldTarget);
    const resp = await sendRuntime({
      type: MSG.WAIT_PROFILE,
      requestId,
      profileUrl,
      user,
      note: { note_id: note.note_id, note_url: note.url, note_title: note.title },
      sourceType,
      comment,
      historyLimit,
      timeoutMs: 22000
    });
    if (!resp || !resp.ok) await progress("profiles", `profile skipped/timeout: ${user.username || key}`);
    return !!(resp && resp.ok);
  }

  async function collectCurrentProfile() {
    await sleep(900);
    const user = collectProfileData();
    if (!user.profile_url) user.profile_url = location.href;
    if (!user.user_id) user.user_id = extractUserId(location.href);
    await sendRuntime({ type: MSG.PROFILE_RESULT, profileUrl: user.profile_url, user });
  }

  function collectProfileData() {
    const root = document;
    const avatar = root.querySelector('img.avatar-item[src], .avatar img[src], img[src*="sns-avatar"]');
    const username =
      text(root.querySelector(".user-name")) ||
      text(root.querySelector(".username")) ||
      text(root.querySelector("[class*='user'][class*='name']")) ||
      text(root.querySelector("h1"));
    const bio =
      text(root.querySelector(".user-desc")) ||
      text(root.querySelector(".desc")) ||
      text(root.querySelector("[class*='user'][class*='desc']"));
    const posts = collectProfilePosts();
    return {
      username,
      user_id: extractUserId(location.href),
      profile_url: location.href,
      avatar_url: avatar ? avatar.src : "",
      bio,
      stats_text: collectStatsText(),
      history_posts: posts,
      profile_collected_at: new Date().toISOString()
    };
  }

  function collectProfilePosts() {
    const rows = [];
    for (const item of Array.from(document.querySelectorAll("section.note-item, .note-item, a[href*='/explore/'], a[href*='/search_result/']")).slice(0, 80)) {
      const link = item.matches("a") ? item : item.querySelector("a[href*='/explore/'], a[href*='/search_result/']");
      if (!link) continue;
      const url = absUrl(link.getAttribute("href"));
      const noteId = extractNoteId(url);
      if (!noteId || rows.some((row) => row.note_id === noteId)) continue;
      rows.push({
        note_id: noteId,
        title: text(item.querySelector(".title")) || text(link),
        url,
        cover_url: (item.querySelector("img[src]") || link.querySelector("img[src]") || {}).src || "",
        like_count_text: text(item.querySelector(".like-wrapper .count, .count")),
        collected_at: new Date().toISOString()
      });
    }
    return rows.slice(0, 30);
  }

  function collectStatsText() {
    return unique(Array.from(document.querySelectorAll("span, div")).map((el) => text(el)).filter((v) => /关注|粉丝|获赞|收藏/.test(v) && v.length < 80)).slice(0, 20);
  }

  async function closeNoteDetail() {
    const close = document.querySelector("#noteContainer [class*='close'], #noteContainer [aria-label*='关闭'], [class*='close'][class*='note'], [aria-label*='关闭']");
    if (close && isVisible(close)) {
      simulateClick(close);
      await sleep(900);
      return;
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", bubbles: true }));
    await sleep(900);
    if (document.querySelector("#noteContainer, #detail-title, #detail-desc")) {
      throw new Error("严格流程停止：没有关闭当前笔记详情，避免继续乱跑。");
    }
  }

  function addUser(out, user, source) {
    if (!user || (!user.profile_url && !user.username)) return;
    const existing = out.find((item) => userKey(item) === userKey(user));
    const payload = Object.assign({}, user, { sources: [Object.assign({}, source, { collected_at: new Date().toISOString() })] });
    if (existing) existing.sources = existing.sources.concat(payload.sources);
    else out.push(payload);
  }

  function findProfileAnchor(profileUrl, userId, comment) {
    const id = userId || extractUserId(profileUrl);
    const commentRoot = comment && comment.comment_id ? document.getElementById(`comment-${comment.comment_id}`) : null;
    if (commentRoot) {
      const scopedLinks = Array.from(commentRoot.querySelectorAll('a[href*="/user/profile/"]'));
      const scoped = scopedLinks.find((a) => id && (a.getAttribute("href") || "").includes(id) && isVisible(a)) ||
        scopedLinks.find((a) => canonical(absUrl(a.getAttribute("href"))) === canonical(profileUrl) && isVisible(a)) ||
        scopedLinks.find((a) => isVisible(a));
      if (scoped) return scoped;
    }
    const links = Array.from(document.querySelectorAll('a[href*="/user/profile/"]'));
    return links.find((a) => id && (a.getAttribute("href") || "").includes(id) && isVisible(a)) ||
      links.find((a) => canonical(absUrl(a.getAttribute("href"))) === canonical(profileUrl) && isVisible(a)) ||
      null;
  }

  function pickNoteLink(card) {
    const links = Array.from(card.querySelectorAll("a[href]"));
    return links.find((a) => /\/search_result\//.test(a.getAttribute("href") || "") && (a.classList.contains("cover") || a.classList.contains("title")) && isVisible(a)) ||
      links.find((a) => /\/search_result\//.test(a.getAttribute("href") || "") && isVisible(a));
  }

  function findNoteClickTarget(noteId) {
    const selector = [
      `section.note-item a.cover[href*="${cssEscape(noteId)}"]`,
      `section.note-item a.title[href*="${cssEscape(noteId)}"]`,
      `section.note-item a[href*="${cssEscape(noteId)}"][href*="/search_result/"]`
    ].join(",");
    return Array.from(document.querySelectorAll(selector)).find(isVisible) || null;
  }

  function simulateClick(el) {
    if (!el) throw new Error("click target missing");
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    for (const type of ["pointerover", "pointermove", "pointerdown", "mousedown", "pointerup", "mouseup"]) {
      const eventInit = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: type.includes("down") ? 1 : 0 };
      if (type.startsWith("pointer")) {
        el.dispatchEvent(new PointerEvent(type, Object.assign({}, eventInit, { pointerId: 1, pointerType: "mouse", isPrimary: true })));
      } else {
        el.dispatchEvent(new MouseEvent(type, eventInit));
      }
    }
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: 0 }));
  }

  function waitFor(fn, timeoutMs, errorMessage) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const tick = () => {
        let value = null;
        try { value = fn(); } catch (_) {}
        if (value) return resolve(value);
        if (Date.now() - start > timeoutMs) return reject(new Error(errorMessage || "wait timeout"));
        setTimeout(tick, 250);
      };
      tick();
    });
  }

  function progress(phase, message) {
    console.log(TAG, phase, message);
    return sendRuntime({ type: MSG.PROGRESS, phase, message });
  }

  function reportError(error) {
    console.warn(TAG, error);
    return sendRuntime({ type: MSG.ERROR, error: errText(error) });
  }

  function sendRuntime(payload) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(payload, (response) => {
          if (chrome.runtime.lastError) return resolve({ ok: false, error: chrome.runtime.lastError.message });
          resolve(response || { ok: true });
        });
      } catch (error) {
        resolve({ ok: false, error: errText(error) });
      }
    });
  }

  function normalizeSettings(input) {
    return {
      keyword: String(input.keyword || "").trim(),
      maxNotes: clamp(input.maxNotes, 1, 200, 10),
      historyLimit: 10,
      profileLimit: clamp(input.profileLimit, 1, 300, 20)
    };
  }

  function detectSearchKeyword() {
    const inputSelectors = [
      'input[type="search"]',
      'input[placeholder*="搜索"]',
      'input[class*="search"]',
      '[contenteditable="true"][class*="search"]'
    ];
    for (const selector of inputSelectors) {
      const node = document.querySelector(selector);
      const value = node && (node.value || node.innerText || node.textContent);
      if (String(value || "").trim()) return String(value).trim();
    }
    try {
      const url = new URL(location.href);
      for (const key of ["keyword", "q", "query", "search_key"]) {
        const value = url.searchParams.get(key);
        if (String(value || "").trim()) return String(value).trim();
      }
    } catch (_) {}
    const title = String(document.title || "")
      .replace(/小红书|搜索|发现|_.*$/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return title.length > 1 && title.length < 80 ? title : "";
  }

  function userKey(user) {
    return user && (user.user_id || extractUserId(user.profile_url || "") || user.profile_url || user.username);
  }

  function countCollectedProfiles(set) {
    return set.size;
  }

  function text(node) {
    return String(node && (node.innerText || node.textContent) || "").replace(/\s+/g, " ").trim();
  }

  function absUrl(href) {
    try { return href ? new URL(href, location.origin).href : ""; } catch (_) { return ""; }
  }

  function canonical(url) {
    return String(url || "").split("#")[0].split("?")[0];
  }

  function extractNoteId(url) {
    const m = String(url || "").match(/\/(?:explore|search_result)\/([^/?#]+)/);
    return m ? m[1] : "";
  }

  function extractUserId(url) {
    const m = String(url || "").match(/\/user\/profile\/([^/?#]+)/);
    return m ? m[1] : "";
  }

  function isVisible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean)));
  }

  function cssEscape(value) {
    return window.CSS && CSS.escape ? CSS.escape(String(value || "")) : String(value || "").replace(/"/g, '\\"');
  }

  function clamp(value, min, max, fallback) {
    const n = parseInt(value, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function errText(error) {
    return String(error && error.message || error || "unknown_error");
  }
})();
