(() => {
  if (window.__DOUYIN_CREATOR_COLLECTOR__) return;
  window.__DOUYIN_CREATOR_COLLECTOR__ = true;

  const TAG = "[DOUYIN-CS]";
  const MSG = {
    CS_START: "DOUYIN_CS_START",
    CS_STOP: "DOUYIN_CS_STOP",
    PROGRESS: "DOUYIN_PROGRESS",
    POST_DONE: "DOUYIN_POST_DONE",
    DONE: "DOUYIN_DONE",
    ERROR: "DOUYIN_ERROR",
    EXPECT_PROFILE: "DOUYIN_EXPECT_PROFILE",
    VERIFY_PROFILE_TAB: "DOUYIN_VERIFY_PROFILE_TAB",
    WAIT_PROFILE: "DOUYIN_WAIT_PROFILE",
    PROFILE_RESULT: "DOUYIN_PROFILE_RESULT",
    OPEN_PROFILE_TAB: "DOUYIN_OPEN_PROFILE_TAB",
    CLOSE_PROFILE_TABS: "DOUYIN_CLOSE_PROFILE_TABS"
  };

  let running = false;
  let stopped = false;
  let doneSent = false;
  let profileResultSent = false;
  let profileCollectionQueue = Promise.resolve();
  let lastProfileOpenAt = 0;
  const PROFILE_OPEN_INTERVAL_MS = 1000;
  const PROFILE_TAB_OPEN_TIMEOUT_MS = 5000;
  const PROFILE_OPEN_FAIL_CLOSE_DELAY_MS = 5000;
  const PROFILE_CLICK_SETTLE_MS = 900;
  const PROFILE_PAGE_COLLECT_DELAYS_MS = [5000, 8500];
  const PROFILE_CONTENT_READY_TIMEOUT_MS = 15000;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || typeof message.type !== "string") return false;
    if (message.type === "DOUYIN_PING") {
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

  if (isDouyinProfilePage()) {
    PROFILE_PAGE_COLLECT_DELAYS_MS.forEach((delay) => {
      setTimeout(() => collectCurrentProfile().catch((e) => console.warn(TAG, "profile auto collect failed", e)), delay);
    });
  }

  async function startRun(settings, runId) {
    if (running) return { alreadyRunning: true };
    running = true;
    stopped = false;
    doneSent = false;
    profileCollectionQueue = Promise.resolve();
    const opts = normalizeSettings(settings);
    opts.keyword = detectSearchKeyword() || opts.keyword;
    try {
      await progress("posts", "严格流程：从当前抖音结果页开始");
      await ensureManualResultPage();
      const cardTarget = searchCardTarget(opts);
      const targetText = opts.limitMode === "profiles"
        ? `采集主页 ${opts.profileLimit} 个，最多预加载 ${cardTarget} 条视频`
        : `视频 ${opts.maxPosts} 条`;
      await progress("posts", `自动滚动加载当前结果页，目标 ${targetText}`);
      const cards = await collectSearchCards(cardTarget);
      if (!cards.length) throw new Error(`当前页面没有可采集的抖音视频卡片。${debugSearchCardCounts()}`);
      await progress("posts", `已锁定当前页面卡片快照：${cards.length} 条`);

      const profileSeen = new Set();
      const profileAttempted = new Set();
      let profileCount = countCollectedProfiles(profileSeen);
      let processedPosts = 0;
      for (let i = 0; i < cards.length && !stopped && !targetReached(profileCount, processedPosts, opts); i += 1) {
        const card = cards[i];
        await progress("posts", `严格流程 ${i + 1}/${cards.length}：打开视频 ${card.title || card.post_id}`);
        const beforeUrl = location.href;
        try {
          await attemptAction("打开视频卡片", () => openPostCard(card), { phase: "posts" });
          await attemptAction("等待视频详情加载", () => waitForPostReady(), { phase: "posts" });
          await progress("posts", `采集视频内容：${card.title || card.post_id}`);
          const post = collectPostDetail(card, opts.keyword, runId);
          const authorUsers = collectUsersFromPost(post, [], opts.keyword);
          await sendRuntime({ type: MSG.POST_DONE, post, comments: [], users: authorUsers });
          processedPosts += 1;
          if (targetReached(profileCount, processedPosts, opts)) {
            await progress("posts", `已达到采集视频数目标：${processedPosts}/${opts.maxPosts}`);
            break;
          }

          profileCount = countCollectedProfiles(profileSeen);
          if (post.author && (post.author.profile_url || post.author.username)) {
            const key = userKey(post.author);
            if (key && !profileSeen.has(key) && !profileAttempted.has(key) && canOpenMoreProfiles(profileCount, opts)) {
              await progress("profiles", "新标签页打开视频作者主页");
              profileAttempted.add(key);
              const ok = await enqueueProfileCollection(() => openProfileInNewTab(post.author, post, "post_author"));
              if (ok) {
                profileSeen.add(key);
                profileCount += 1;
                if (targetReached(profileCount, processedPosts, opts)) {
                  await progress("profiles", `已达到采集主页数目标：${profileCount}/${opts.profileLimit}`);
                  break;
                }
              }
            }
          }

          await progress("comments", "开始采集评论区评论");
          profileCount = await processCommentsStepByStep(post, opts, profileSeen, profileAttempted, profileCount);
          if (profileTargetReached(profileCount, opts)) {
            await progress("profiles", `已达到采集主页数目标：${profileCount}/${opts.profileLimit}`);
          }
        } catch (error) {
          if (stopped) break;
          await progress("posts", `当前视频超时/异常，页面状态：${formatPageAnalysis(analyzeCurrentPage())}；跳过并继续下一个。原因：${errText(error)}`);
        } finally {
          await progress("posts", "关闭当前视频详情，回到原结果页");
          await attemptAction("关闭当前视频详情", () => closePostDetail(beforeUrl), { phase: "posts", throwOnFail: false });
          await attemptAction("恢复结果页", () => recoverResultPageAfterTimeout(beforeUrl), { phase: "posts", requireTruthy: true, throwOnFail: false });
        }
        await sleep(700);
      }

      running = false;
      await sendDoneOnce(stopped ? "已停止" : "采集完成");
      return { ok: true, stopped };
    } catch (error) {
      running = false;
      throw error;
    }
  }

  async function ensureManualResultPage() {
    await waitFor(
      () => findVisualSearchCardRoots().length > 0,
      9000,
      "当前页面没有抖音搜索结果视频卡片，请先人工打开并加载抖音搜索结果页。"
    );
  }

  async function recoverResultPageAfterTimeout(beforeUrl) {
    const snapshot = analyzeCurrentPage();
    if (snapshot.isSearch && !snapshot.isDetail && !snapshot.isProfile) return true;
    if (snapshot.isDetail || snapshot.isProfile || canonical(location.href) !== canonical(beforeUrl || "")) {
      if (beforeUrl && /^https?:\/\//i.test(beforeUrl) && canonical(location.href) !== canonical(beforeUrl)) {
        history.back();
        await sleep(1200);
      } else {
        await closePostDetail(beforeUrl).catch(() => undefined);
      }
    }
    try {
      await ensureManualResultPage();
      return true;
    } catch (error) {
      await progress("posts", `回到结果页超时，页面状态：${formatPageAnalysis(analyzeCurrentPage())}；继续尝试下一条。`);
      return false;
    }
  }

  async function collectSearchCards(maxPosts) {
    const cards = new Map();
    let stable = 0;
    let lastCount = 0;
    const scroller = getSearchResultScroller();

    for (let round = 0; round < 45 && cards.size < maxPosts && stable < 7 && !stopped; round += 1) {
      collectSearchCardsFromDom(cards, maxPosts);
      if (cards.size !== lastCount) {
        await progress("posts", `已加载抖音结果卡片 ${cards.size}/${maxPosts}`);
        stable = 0;
        lastCount = cards.size;
      } else {
        stable += 1;
      }
      if (cards.size >= maxPosts || stable >= 7) break;
      scrollSearchResult(scroller, 1100);
      await sleep(850);
    }

    collectSearchCardsFromDom(cards, maxPosts);
    scrollSearchResult(scroller, -1000000);
    await sleep(600);
    return Array.from(cards.values()).slice(0, maxPosts);
  }

  function searchCardTarget(opts) {
    if (opts.limitMode === "profiles") {
      return clamp(Math.max(opts.profileLimit, opts.maxPosts || 0, 10), 1, 200, 20);
    }
    return opts.maxPosts;
  }

  function collectSearchCardsFromDom(cards, maxPosts) {
    let added = collectDouyinWaterfallCardsFromDom(cards, maxPosts, 0);
    if (cards.size >= maxPosts) return added;

    const links = Array.from(document.querySelectorAll('a[href*="/video/"], a[href*="/note/"]'));
    for (const [sourceIndex, link] of links.entries()) {
      if (!isVisible(link)) continue;
      const url = absUrl(link.getAttribute("href") || link.href || "");
      if (!/douyin\.com\/(?:video|note)\//i.test(url)) continue;
      const postId = extractPostId(url);
      const key = postId || canonical(url);
      if (!key || cards.has(key)) continue;
      const card = findCardContainer(link);
      const author = findAuthorLink(card) || findAuthorLink(link.closest("div"));
      const visible = text(card || link);
      const meta = pickSearchCardMeta(card || link);
      cards.set(key, {
        post_id: postId,
        source_index: sourceIndex,
        title: pickTitleText(card, link, visible),
        post_url: url,
        cover_url: pickImage(card || link),
        image_urls: collectImageUrls(card || link),
        content_type: meta.content_type,
        duration: meta.duration,
        published_at_text: meta.published_at_text,
        author_username: author ? text(author) : "",
        author_profile_url: author ? absUrl(author.getAttribute("href") || author.href || "") : "",
        like_count_text: pickMetricText(card, /赞|喜欢|like/i),
        comment_count_text: pickMetricText(card, /评论|comment/i),
        collected_at: new Date().toISOString()
      });
      added += 1;
      if (cards.size >= maxPosts) break;
    }
    if (cards.size < maxPosts) {
      added += collectSearchVisualCardsFromDom(cards, maxPosts, added + links.length);
    }
    return added;
  }

  function collectDouyinWaterfallCardsFromDom(cards, maxPosts, sourceOffset) {
    let added = 0;
    const roots = findDouyinSearchCardRoots();
    for (const [index, card] of roots.entries()) {
      if (cards.size >= maxPosts) break;
      const clickTarget = findVisualPostClickTarget(card);
      if (!clickTarget) continue;
      const visible = text(card);
      const title = pickTitleText(card, clickTarget, visible);
      if (!title || title.length < 2) continue;
      const postUrl = pickPostUrl(card);
      const postId = extractPostId(postUrl) || extractWaterfallPostId(card);
      const key = postId || `waterfall:${card.id || ""}:${hashText(title).slice(0, 10)}`;
      if (!key || cards.has(key)) continue;
      const author = findAuthorLink(card) || findVisualAuthorNode(card);
      const meta = pickSearchCardMeta(card);
      const row = {
        post_id: postId,
        source_index: sourceOffset + index,
        title,
        post_url: postUrl,
        cover_url: pickImage(card),
        image_urls: collectImageUrls(card),
        content_type: meta.content_type,
        duration: meta.duration,
        published_at_text: meta.published_at_text,
        author_username: author ? text(author).replace(/^@\s*/, "") : "",
        author_profile_url: author && author.getAttribute ? absUrl(author.getAttribute("href") || author.href || "") : "",
        like_count_text: pickMetricText(card, /赞|喜欢|like/i),
        comment_count_text: pickMetricText(card, /评论|comment/i),
        collected_at: new Date().toISOString()
      };
      row._clickTarget = clickTarget;
      row._waterfallId = card.id || "";
      cards.set(key, row);
      added += 1;
    }
    return added;
  }

  function collectSearchVisualCardsFromDom(cards, maxPosts, sourceOffset) {
    let added = 0;
    const roots = findVisualSearchCardRoots();
    for (const [index, card] of roots.entries()) {
      if (cards.size >= maxPosts) break;
      const clickTarget = findVisualPostClickTarget(card);
      if (!clickTarget) continue;
      const visible = text(card);
      const title = pickTitleText(card, clickTarget, visible);
      if (!title || title.length < 4) continue;
      const postUrl = pickPostUrl(card);
      const postId = extractPostId(postUrl) || extractWaterfallPostId(card) || String(card.getAttribute("data-id") || card.getAttribute("data-item-id") || "");
      const rect = card.getBoundingClientRect();
      const key = postId || canonical(postUrl) || `visual:${Math.round(rect.left)}:${Math.round(rect.top)}:${hashText(title).slice(0, 10)}`;
      if (!key || cards.has(key)) continue;
      const author = findAuthorLink(card) || findVisualAuthorNode(card);
      const meta = pickSearchCardMeta(card);
      const row = {
        post_id: postId,
        source_index: sourceOffset + index,
        title,
        post_url: postUrl,
        cover_url: pickImage(card),
        image_urls: collectImageUrls(card),
        content_type: meta.content_type,
        duration: meta.duration,
        published_at_text: meta.published_at_text,
        author_username: author ? text(author).replace(/^@\s*/, "") : "",
        author_profile_url: author && author.getAttribute ? absUrl(author.getAttribute("href") || author.href || "") : "",
        like_count_text: pickMetricText(card, /赞|喜欢|like/i),
        comment_count_text: pickMetricText(card, /评论|comment/i),
        collected_at: new Date().toISOString()
      };
      row._clickTarget = clickTarget;
      cards.set(key, row);
      added += 1;
    }
    return added;
  }

  function getSearchResultScroller() {
    const waterfall = document.querySelector("#waterFallScrollContainer");
    const candidates = [
      waterfall && waterfall.parentElement,
      waterfall,
      document.querySelector('[data-e2e*="search"]'),
      document.querySelector('[class*="search"]'),
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

  async function openPostCard(card) {
    const postId = card.post_id || extractPostId(card.post_url);
    const target = findPostClickTarget(postId, card.post_url, card);
    if (!target) throw new Error("严格流程停止：当前已加载页面中没有找到可点击视频：" + (postId || card.post_url));
    target.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(250);
    simulateClick(target);
    await sleep(1000);
  }

  async function waitForPostReady() {
    try {
      await waitFor(() => {
        const hasPostUrl = /douyin\.com\/(?:video|note)\//i.test(location.href);
        const hasActionBar = Boolean(findDetailActionBar());
        const hasAuthor = Boolean(findVideoAuthorAnchor());
        const hasMedia = Boolean(document.querySelector("video, picture, canvas, img[src]"));
        return hasActionBar && (hasAuthor || hasMedia || hasPostUrl);
      }, 14000, "视频详情没有加载完成：未识别到抖音详情页 action bar");
    } catch (error) {
      const snapshot = analyzeCurrentPage();
      if (snapshot.isDetail && (snapshot.hasActionBar || snapshot.hasMedia || snapshot.hasPostUrl)) {
        await progress("posts", `视频详情等待超时，但页面已有可采集内容：${formatPageAnalysis(snapshot)}；继续采集当前视频。`);
      } else {
        throw new Error(`${errText(error)}；${formatPageAnalysis(snapshot)}`);
      }
    }
    await sleep(900);
  }

  function collectPostDetail(card, keyword, runId) {
    const root = findDetailRoot() || document;
    const infoRoot = findVideoInfoRoot(root) || findVideoInfoRoot(document) || root;
    const actionBar = findDetailActionBar();
    const authorAnchor = findVideoAuthorAnchor(root) || findAuthorLink(infoRoot) || findAuthorLink(root);
    const authorUrl = authorAnchor ? absUrl(authorAnchor.getAttribute("href") || authorAnchor.href || "") : card.author_profile_url || "";
    const desc = pickDescriptionText(infoRoot, card.title || "") || pickDescriptionText(root, card.title || "");
    const authorName = pickDetailAuthorName(root, infoRoot, card, authorAnchor, desc);
    const detailUrl = /douyin\.com\/(?:video|note)\//i.test(location.href) ? location.href : "";
    const sourcePageUrl = detailUrl ? "" : location.href;
    const cardPostUrl = /douyin\.com\/(?:video|note)\//i.test(card.post_url || "") ? card.post_url : "";
    const modalPostId = extractModalPostId(location.href) || extractModalPostId(card.post_url);
    const awemeId = pickAwemeId(root, infoRoot, detailUrl || cardPostUrl || location.href) || modalPostId || card.post_id || "";
    const inferredPostId = extractPostId(detailUrl || cardPostUrl) || card.post_id || awemeId || "";
    const postUrl = detailUrl || cardPostUrl || postUrlFromId(inferredPostId) || "";
    const fallbackPostId = `local-${hashText([runId, card.source_index, card.title, card.cover_url].join("|"))}`;
    const postId = extractPostId(postUrl) || inferredPostId || fallbackPostId;
    const likeText = pickActionMetric('[data-e2e="video-player-digg"]') || pickMetricText(actionBar || root, /赞|喜欢|like/i) || card.like_count_text || "";
    const commentText = pickActionMetric('[data-e2e="feed-comment-icon"]') || pickMetricText(actionBar || root, /评论|comment/i) || card.comment_count_text || "";
    const collectNode = document.querySelector('[data-e2e="video-player-collect"]');
    const shareNode = document.querySelector('[data-e2e="video-player-share"]');
    const collectText = pickActionMetric('[data-e2e="video-player-collect"]') || pickCompactText(collectNode);
    const shareText = pickActionMetric('[data-e2e="video-player-share"]') || pickCompactText(shareNode);
    const imageUrls = collectImageUrls(root);
    const mediaUrls = collectMediaUrls(root);
    const publishedAtText = pickDetailCreateTime(infoRoot) || pickTimeText(infoRoot) || card.published_at_text || "";
    const contentType = pickDetailContentType(infoRoot, root, card);
    return {
      platform: "douyin",
      keyword,
      run_id: runId,
      post_id: postId,
      video_id: postId,
      aweme_id: awemeId || postId,
      content_type: contentType,
      title: desc || card.title || "",
      desc,
      source_index: card.source_index,
      published_at_text: publishedAtText,
      duration: pickDurationText(root) || card.duration || "",
      cover_url: card.cover_url || pickCoverImage(root) || pickImage(root),
      image_urls: unique([].concat(card.image_urls || [], imageUrls)),
      media_url: mediaUrls[0] || pickMediaUrl(root),
      media_urls: mediaUrls,
      url: postUrl,
      post_url: postUrl,
      source_page_url: sourcePageUrl || "",
      search_result_url: sourcePageUrl || "",
      like_count_text: likeText,
      comment_count_text: commentText,
      comment_count: parseMetricNumber(commentText),
      collect_count_text: collectText,
      collect_state: collectNode ? String(collectNode.getAttribute("data-e2e-state") || "") : "",
      share_count_text: shareText,
      metrics: {
        like_count_text: likeText,
        comment_count_text: commentText,
        comment_count: parseMetricNumber(commentText),
        collect_count_text: collectText,
        collect_state: collectNode ? String(collectNode.getAttribute("data-e2e-state") || "") : "",
        share_count_text: shareText
      },
      comment_collection_status: "pending",
      author: {
        username: authorName,
        profile_url: authorUrl,
        user_id: extractUserId(authorUrl),
        avatar_url: pickAvatar(authorAnchor) || pickAvatar(root)
      },
      collected_at: new Date().toISOString()
    };
  }

  async function processCommentsStepByStep(post, opts, profileSeen, profileAttempted, profileCount) {
    const expectedCount = Number.isFinite(post.comment_count) ? post.comment_count : parseMetricNumber(post.comment_count_text);
    let panel = await attemptAction("打开评论区", () => openCommentPanelIfNeeded(post), {
      phase: "comments",
      requireTruthy: expectedCount > 0,
      throwOnFail: false
    });
    if (!panel) {
      post.comment_count_collected = 0;
      post.comment_collection_status = expectedCount > 0 ? "skipped" : "complete";
      post.comment_collection_error = expectedCount > 0 ? `comment panel unavailable; ${formatPageAnalysis(analyzeCurrentPage())}` : "";
      await sendRuntime({ type: MSG.POST_DONE, post, comments: [], users: [] });
      await progress("comments", expectedCount > 0 ? "评论区不可用，跳过评论采集并进入下一步" : "无评论或评论区未出现，进入下一步");
      return profileCount;
    }
    let scroller = findCommentScroller(panel) || closestScrollable(panel) || findCommentScroller() || panel || document.scrollingElement || document.body;
    await scrollCommentPanelToStart(panel);
    let stable = 0;
    const seenComments = new Set();
    const skippedReplyExpandRows = new Set();
    const pendingReplyExpandRows = new Map();
    const replyExpandAttempts = new Map();
    for (let round = 0; round < 120 && stable < 8 && !stopped; round += 1) {
      panel = findCommentPanelRoot(panel) || panel;
      scroller = findCommentScroller(panel) || closestScrollable(panel) || findCommentScroller() || scroller;
      const visibleRows = findCommentRows(panel)
        .filter((row) => isInCommentViewport(row, scroller, 100))
        .sort(sortByPosition);

      let didWork = false;
      for (let index = 0; index < visibleRows.length && !stopped; index += 1) {
        const row = visibleRows[index];
        const comment = collectCommentFromRow(post, row, panel, index, visibleRows);
        if (!comment) continue;
        const key = commentIdentityKey(comment);
        if (key && !seenComments.has(key)) {
          seenComments.add(key);
          const tx = await handleCommentRowTransaction(row, comment, post, opts, {
            profileSeen,
            profileAttempted,
            profileCount,
            pendingReplyExpandRows
          });
          profileCount = tx.profileCount;
          await progress("comments", `顺序采集评论 ${seenComments.size}：${comment.user?.username || ""}`);
          didWork = true;
          if (profileTargetReached(profileCount, opts)) {
            await progress("profiles", `已达到采集主页数目标：${profileCount}/${opts.profileLimit}`);
            return profileCount;
          }
          if (tx.rereadDom) break;
        }

        const expandKey = key || commentIdentityKey(comment);
        if (!expandKey || (!skippedReplyExpandRows.has(expandKey) && !pendingReplyExpandRows.has(expandKey))) {
          const attempts = expandKey ? (replyExpandAttempts.get(expandKey) || 0) : 0;
          if (expandKey && attempts >= 3) {
            skippedReplyExpandRows.add(expandKey);
            await progress("comments", "当前评论回复展开连续 3 次没有新回复，跳过该评论的回复展开");
            continue;
          }
          const expandResult = await clickCommentExpandersForRow(row, panel, scroller);
          if (expandResult.failed) {
            if (expandKey) skippedReplyExpandRows.add(expandKey);
            await progress("comments", `展开评论回复失败，跳过该评论的回复展开：${expandResult.error || ""}`);
            didWork = true;
            continue;
          }
          if (expandResult.clicked) {
            if (expandKey) {
              const nextAttempts = attempts + 1;
              replyExpandAttempts.set(expandKey, nextAttempts);
              pendingReplyExpandRows.set(expandKey, { seenCount: seenComments.size, attempts: nextAttempts });
            }
            await progress("comments", "已处理当前评论，只展开 1 个回复入口并重新识别当前页");
            await sleep(700);
            didWork = true;
            break;
          }
        }
      }

      if (!didWork && pendingReplyExpandRows.size) {
        const released = await releasePendingReplyExpands(pendingReplyExpandRows, skippedReplyExpandRows, replyExpandAttempts);
        if (released) {
          stable = 0;
          await sleep(260);
          continue;
        }
      }

      if (!didWork) {
        stable += 1;
      } else {
        stable = 0;
        await sleep(260);
        continue;
      }

      if (hasCommentEndMarker(panel || findCommentPanelRoot())) {
        await progress("comments", "评论区已加载到底");
        break;
      }

      await progress("comments", "当前可见评论已按顺序处理完，下滑加载下一页评论");
      scroller = findCommentScroller(panel) || closestScrollable(panel) || findCommentScroller() || scroller;
      scrollCommentPanelBy(scroller, commentPageScrollDelta(scroller));
      await sleep(850);
      if (hasCommentEndMarker(panel || findCommentPanelRoot())) {
        await progress("comments", "评论区已加载到底");
        break;
      }
    }
    post.comment_count_collected = seenComments.size;
    if (expectedCount > 0 && seenComments.size === 0) {
      post.comment_collection_status = "incomplete";
      post.comment_collection_error = `expected ${expectedCount} comments but collected 0 after opening comment panel; ${formatPageAnalysis(analyzeCurrentPage())}`;
      await sendRuntime({ type: MSG.POST_DONE, post, comments: [], users: [] });
      await progress("comments", "评论区没有采到可用评论，跳过评论并进入下一步");
      return profileCount;
    }
    post.comment_collection_status = "complete";
    await sendRuntime({ type: MSG.POST_DONE, post, comments: [], users: [] });
    return profileCount;
  }

  async function openCommentPanelIfNeeded(post) {
    const expectedCount = Number.isFinite(post.comment_count) ? post.comment_count : parseMetricNumber(post.comment_count_text);
    const detailRoot = findDetailRoot();
    let panel = findCommentPanelRoot(detailRoot);
    if (hasOpenedCommentPanel(panel, detailRoot)) return panel;

    const button = findCommentOpenButton(detailRoot);
    if (!button) {
      if (expectedCount > 0) {
        await progress("comments", `未找到评论按钮，页面状态：${formatPageAnalysis(analyzeCurrentPage())}；跳过评论区并进入下一步。`);
      }
      return null;
    }

    await progress("comments", "打开评论区");
    button.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(180);
    simulateClick(button);
    try {
      panel = await waitFor(() => {
        const currentRoot = findDetailRoot() || detailRoot;
        const current = findCommentPanelRoot(currentRoot);
        return hasOpenedCommentPanel(current, currentRoot) ? current : null;
      }, 12000, "评论区未展开");
    } catch (error) {
      const snapshot = analyzeCurrentPage();
      const currentRoot = findDetailRoot() || detailRoot;
      const current = findCommentPanelRoot(currentRoot);
      if (hasOpenedCommentPanel(current, currentRoot)) return current;
      await progress("comments", `评论区等待超时，页面状态：${formatPageAnalysis(snapshot)}；跳过评论区并进入下一步。原因：${errText(error)}`);
      return null;
    }
    await sleep(650);
    return panel;
  }

  async function clickCommentExpandersForRow(row, panel, scroller) {
    if (!row || !panel) return { clicked: 0, failed: false };
    const rowRect = row.getBoundingClientRect();
    const nextRoot = findNextRootCommentRow(row, panel);
    const nextTop = nextRoot ? nextRoot.getBoundingClientRect().top : Number.POSITIVE_INFINITY;
    const maxY = Number.isFinite(nextTop) ? Math.max(rowRect.bottom, nextTop - 2) : rowRect.bottom + 220;
    for (const el of findCommentExpanderElements(panel)) {
      if (!isInCommentViewport(el, scroller || panel, 80)) continue;
      const rect = el.getBoundingClientRect();
      const belongsToRow = row.contains(el) || (rect.top >= rowRect.top - 8 && rect.top <= maxY);
      if (!belongsToRow) continue;
      await waitReplyExpandFailureToastGone();
      try {
        simulateClick(el);
        await sleep(520);
        const error = replyExpandFailureToastText();
        if (error) {
          await waitReplyExpandFailureToastGone();
          return { clicked: 0, failed: true, error };
        }
        return { clicked: 1, failed: false };
      } catch (error) {
        return { clicked: 0, failed: true, error: errText(error) };
      }
    }
    return { clicked: 0, failed: false };
  }

  function replyExpandFailureToastText() {
    const re = /展开回复失败|回复失败|评论失败|加载失败|reply.*fail|load.*fail/i;
    const nodes = Array.from(document.querySelectorAll('[data-e2e="toast"], [role="alert"], [class*="toast"], [class*="Toast"]'));
    for (const node of nodes) {
      if (!isVisible(node)) continue;
      const value = text(node);
      if (value && re.test(value)) return value;
    }
    return "";
  }

  async function waitReplyExpandFailureToastGone() {
    for (let i = 0; i < 10; i += 1) {
      if (!replyExpandFailureToastText()) return true;
      await sleep(250);
    }
    return false;
  }

  function resolvePendingReplyExpandForComment(comment, pendingReplyExpandRows) {
    if (!comment || !pendingReplyExpandRows || comment.depth <= 0) return;
    for (const key of [comment.root_comment_id, comment.parent_comment_id]) {
      if (key && pendingReplyExpandRows.has(key)) pendingReplyExpandRows.delete(key);
    }
  }

  async function releasePendingReplyExpands(pendingReplyExpandRows, skippedReplyExpandRows, replyExpandAttempts) {
    let released = false;
    for (const [key, meta] of Array.from(pendingReplyExpandRows.entries())) {
      pendingReplyExpandRows.delete(key);
      released = true;
      if ((replyExpandAttempts.get(key) || meta.attempts || 0) >= 3) {
        skippedReplyExpandRows.add(key);
        await progress("comments", "当前评论回复展开连续 3 次没有新回复，跳过该评论的回复展开");
      } else {
        await progress("comments", "展开后没有识别到新回复，释放当前评论并继续下一步判断");
      }
    }
    return released;
  }

  function findCommentExpanderElements(scope) {
    const re = /展开|查看更多|更多回复|查看.*回复|全部回复|展开.*评论|show|more|reply/i;
    const root = scope && scope.querySelectorAll ? scope : document;
    return Array.from(root.querySelectorAll("button, div, span, a"))
      .filter((el) => {
        const value = text(el);
        if (!value || value.length > 40 || !re.test(value) || !isVisible(el)) return false;
        if (/失败|failed/i.test(value)) return false;
        if (el.closest('[data-e2e="toast"], [role="alert"], [class*="toast"], [class*="Toast"]')) return false;
        return true;
      })
      .sort(sortByPosition);
  }

  function findNextRootCommentRow(row, panel) {
    if (!row) return null;
    const currentTop = row.getBoundingClientRect().top;
    return findCommentRows(panel || findCommentPanelRoot() || document)
      .filter((candidate) => candidate !== row)
      .filter((candidate) => candidate.getBoundingClientRect().top > currentTop + 4)
      .filter((candidate) => inferCommentDepth(candidate, panel) === 0)
      .sort(sortByPosition)[0] || null;
  }

  function collectComments(post, scope, options) {
    const opts = options || {};
    const rows = [];
    const panel = scope || findCommentPanelRoot() || findCommentScroller() || document;
    const candidates = findCommentRows(panel).filter((row) => !opts.visibleOnly || isInCommentViewport(row, opts.scroller || panel, 120));
    for (const [index, item] of candidates.entries()) {
      const row = collectCommentFromRow(post, item, panel, index, candidates);
      if (!row) continue;
      rows.push(row);
    }
    return rows;
  }

  function collectCommentFromRow(post, item, panel, index, contextRows) {
    const author = findAuthorLink(item);
    if (!author) return null;
    const profileUrl = absUrl(author.getAttribute("href") || author.href || "");
    if (!/douyin\.com\/user\//i.test(profileUrl)) return null;
    const username = pickCommentUsername(item, author);
    const content = pickCommentContent(item, username);
    if (!content || content.length < 2 || content.length > 500) return null;
    const commentId = pickCommentId(item) || `${post.post_id || ""}-${extractUserId(profileUrl)}-${hashText(content).slice(0, 10)}`;
    const depth = inferCommentDepth(item, panel);
    const parent = depth > 0 ? findParentCommentForRow(post, item, panel, contextRows || []) : null;
    const meta = pickCommentMeta(item);
    const row = {
      comment_id: commentId,
      root_comment_id: parent?.root_comment_id || parent?.comment_id || commentId,
      parent_comment_id: parent?.comment_id || "",
      depth,
      content,
      published_at_text: meta.published_at_text || pickTimeText(item),
      location: meta.location || pickLocationText(item),
      like_count_text: pickCommentLikeText(item) || pickMetricText(item, /赞|like/i),
      post_id: post.post_id,
      post_title: post.title,
      post_url: post.url,
      user: {
        username,
        profile_url: profileUrl,
        user_id: extractUserId(profileUrl),
        avatar_url: pickAvatar(item)
      },
      collected_at: new Date().toISOString(),
      position: index
    };
    attachCommentDomRefs(row, item, author);
    return row;
  }

  function findParentCommentForRow(post, item, panel, contextRows) {
    if (!item || typeof item.getBoundingClientRect !== "function") return null;
    const currentTop = item.getBoundingClientRect().top;
    const rows = (contextRows && contextRows.length ? contextRows : findCommentRows(panel || findCommentPanelRoot() || document))
      .filter((row) => row !== item && row.getBoundingClientRect().top < currentTop - 2)
      .sort(sortByPosition)
      .reverse();
    const parentRow = rows.find((row) => inferCommentDepth(row, panel) === 0) || rows[0] || null;
    return parentRow ? collectCommentFromRow(post || { post_id: "", title: "", url: "" }, parentRow, panel, 0, []) : null;
  }

  async function handleCommentRowTransaction(row, comment, post, opts, state) {
    if (row && comment) attachCommentDomRefs(comment, row, findAuthorLink(row));
    const nextProfileCount = await recordCommentAndCollectProfile(
      comment,
      post,
      opts,
      state.profileSeen,
      state.profileAttempted,
      state.profileCount
    );
    resolvePendingReplyExpandForComment(comment, state.pendingReplyExpandRows);
    return { profileCount: nextProfileCount, rereadDom: true };
  }

  async function recordCommentAndCollectProfile(comment, post, opts, profileSeen, profileAttempted, profileCount) {
    const users = collectUsersFromPost(post, [comment], opts.keyword)
      .filter((user) => user.sources && user.sources.some((s) => s.source_type === "comment"));
    await sendRuntime({ type: MSG.POST_DONE, comments: [comment], users });
    const commentKey = userKey(comment.user);
    const user = users.find((item) => userKey(item) === commentKey) || comment.user;
    if (!user || !user.profile_url) return profileCount;
    const key = userKey(user);
    if (!key || profileSeen.has(key) || profileAttempted.has(key) || !canOpenMoreProfiles(profileCount, opts)) return profileCount;
    const verified = verifyCommentProfileTarget(user, comment);
    if (!verified.ok) {
      await progress("profiles", `评论用户信息核对未通过，跳过主页：${user.username || key} - ${verified.reason}`);
      return profileCount;
    }
    profileAttempted.add(key);
    await progress("profiles", `评论用户信息已核对，准备采集主页：${user.username || key}`);
    const ok = await enqueueProfileCollection(() => openProfileInNewTab(user, post, "comment", comment, verified.anchor));
    if (ok) {
      profileSeen.add(key);
      profileCount += 1;
    }
    return profileCount;
  }

  function enqueueProfileCollection(task) {
    const run = profileCollectionQueue
      .catch(() => undefined)
      .then(async () => {
        if (stopped) return false;
        return task();
      });
    profileCollectionQueue = run.then(() => undefined, () => undefined);
    return run;
  }

  async function sendDoneOnce(message) {
    if (doneSent) return;
    doneSent = true;
    await sendRuntime({ type: MSG.DONE, message });
  }

  function commentIdentityKey(comment) {
    return comment && (comment.comment_id || `${comment.user?.profile_url || ""}:${comment.content || ""}`);
  }

  function collectUsersFromPost(post, comments, keyword) {
    const out = [];
    addUser(out, post.author, {
      source_type: "post_author",
      keyword,
      post_id: post.post_id,
      post_title: post.title,
      post_url: post.url
    });
    for (const comment of comments) {
      addUser(out, comment.user, {
        source_type: "comment",
        keyword,
        post_id: post.post_id,
        post_title: post.title,
        post_url: post.url,
        comment_id: comment.comment_id,
        comment_depth: comment.depth,
        comment_content: comment.content,
        comment_published_at_text: comment.published_at_text,
        comment_location: comment.location
      });
    }
    return out;
  }

  function findVisibleCommentProfileMatch(user, comment, panel) {
    const profileUrl = user && user.profile_url || "";
    const id = user && (user.user_id || extractUserId(profileUrl));
    const expectedContent = normalizeCommentMatchText(comment && comment.content);
    const rows = findCommentRows(panel || findCommentPanelRoot() || document);
    for (const row of rows) {
      const anchor = findAuthorLink(row);
      if (!anchor || !anchorMatchesProfile(anchor, profileUrl, id)) continue;
      const rowCommentId = pickCommentId(row);
      if (comment && comment.comment_id && rowCommentId && rowCommentId === comment.comment_id) return { row, anchor };
      const rowContent = normalizeCommentMatchText(pickCommentContent(row, text(anchor).replace(/^@\s*/, "")));
      if (expectedContent && rowContent && (rowContent.includes(expectedContent) || expectedContent.includes(rowContent))) {
        return { row, anchor };
      }
    }
    return null;
  }

  function locateLiveCommentProfileAnchor(user, comment) {
    if (!user || !comment) return null;
    const profileUrl = user.profile_url || (comment.user && comment.user.profile_url) || "";
    const id = user.user_id || extractUserId(profileUrl);
    if (comment._profileAnchor && isConnectedNode(comment._profileAnchor) && anchorMatchesProfile(comment._profileAnchor, profileUrl, id)) {
      return comment._profileAnchor;
    }
    const panel = findCommentPanelRoot() || document;
    const match = findVisibleCommentProfileMatch(user, comment, panel);
    if (match && match.row && match.anchor && isVisible(match.row) && isVisible(match.anchor)) {
      attachCommentDomRefs(comment, match.row, match.anchor);
      return match.anchor;
    }
    const rows = findCommentRows(panel).filter((row) => isVisible(row)).sort(sortByPosition);
    const expectedContent = normalizeCommentMatchText(comment.content || "");
    const expectedCommentId = comment.comment_id || "";
    for (const row of rows) {
      const anchor = findAuthorLink(row);
      if (!anchor || !isVisible(anchor) || !anchorMatchesProfile(anchor, profileUrl, id)) continue;
      const rowCommentId = pickCommentId(row);
      if (expectedCommentId && rowCommentId && rowCommentId !== expectedCommentId) continue;
      const rowContent = normalizeCommentMatchText(pickCommentContent(row, text(anchor).replace(/^@\s*/, "")));
      if (expectedContent && rowContent && !(rowContent.includes(expectedContent) || expectedContent.includes(rowContent))) continue;
      attachCommentDomRefs(comment, row, anchor);
      return anchor;
    }
    return null;
  }

  function verifyCommentProfileTarget(user, comment) {
    if (!user || !comment) return { ok: false, reason: "missing user/comment" };
    const profileUrl = user.profile_url || (comment.user && comment.user.profile_url) || "";
    const expectedId = user.user_id || extractUserId(profileUrl);
    if (!profileUrl || !/douyin\.com\/user\//i.test(profileUrl)) {
      return { ok: false, reason: "invalid profile url" };
    }
    const commentUser = comment.user || {};
    const commentProfileUrl = commentUser.profile_url || "";
    const commentId = commentUser.user_id || extractUserId(commentProfileUrl);
    if (commentId && expectedId && commentId !== expectedId) {
      return { ok: false, reason: "comment user id mismatch" };
    }
    if (commentProfileUrl && canonical(commentProfileUrl) !== canonical(profileUrl)) {
      return { ok: false, reason: "comment profile url mismatch" };
    }
    const anchor = locateLiveCommentProfileAnchor(user, comment);
    if (!anchor) {
      return { ok: true, anchor: null, row: null, urlOnly: true, reason: "avatar/profile link not visible; fallback to stored profile url" };
    }
    if (!anchorMatchesProfile(anchor, profileUrl, expectedId)) {
      return { ok: false, reason: "avatar link mismatch" };
    }
    const row = comment._row && isConnectedNode(comment._row)
      ? comment._row
      : findVisibleCommentProfileMatch(user, comment, findCommentPanelRoot() || document)?.row;
    const expectedContent = normalizeCommentMatchText(comment.content || "");
    const rowContent = row ? normalizeCommentMatchText(pickCommentContent(row, text(anchor).replace(/^@\s*/, ""))) : "";
    if (expectedContent && rowContent && !(rowContent.includes(expectedContent) || expectedContent.includes(rowContent))) {
      return { ok: false, reason: "comment text mismatch" };
    }
    const expectedName = normalizeIdentityText(user.username || commentUser.username || "");
    const anchorName = normalizeIdentityText(text(anchor).replace(/^@\s*/, ""));
    if (expectedName && anchorName && expectedName !== anchorName && !expectedName.includes(anchorName) && !anchorName.includes(expectedName)) {
      return { ok: false, reason: "username mismatch" };
    }
    attachCommentDomRefs(comment, row, anchor);
    return { ok: true, anchor, row };
  }

  function isConnectedNode(node) {
    return Boolean(node && (node.isConnected || document.contains(node)));
  }

  function normalizeIdentityText(value) {
    return cleanCommentText(value).replace(/^@+/, "").replace(/\s+/g, "").toLowerCase().slice(0, 80);
  }

  async function scrollCommentPanelToStart(panel) {
    let currentPanel = findCommentPanelRoot(panel) || panel || findCommentPanelRoot();
    const scroller = findCommentScroller(currentPanel) || closestScrollable(currentPanel) || currentPanel;
    for (let i = 0; i < 10; i += 1) {
      const before = getScrollTop(scroller);
      scrollCommentPanelTo(scroller, 0);
      await sleep(260);
      if (Math.abs(getScrollTop(scroller) - before) < 4 || getScrollTop(scroller) <= 4) break;
      currentPanel = findCommentPanelRoot(currentPanel) || currentPanel;
    }
  }

  function scrollCommentPanelBy(panel, delta) {
    const scroller = findCommentScroller(panel) || closestScrollable(panel) || panel || document.scrollingElement || document.body;
    const before = getScrollTop(scroller);
    if (scroller === document.scrollingElement || scroller === document.body || scroller === document.documentElement) {
      window.scrollBy(0, delta);
    } else {
      scroller.scrollTop = scroller.scrollTop + delta;
    }
    return Math.abs(getScrollTop(scroller) - before) > 4;
  }

  function commentPageScrollDelta(scroller) {
    const target = scroller || document.scrollingElement || document.body;
    const height = target === document.scrollingElement || target === document.body || target === document.documentElement
      ? window.innerHeight
      : target.clientHeight;
    return Math.max(520, Math.round((height || 760) * 0.82));
  }

  function isInCommentViewport(node, scroller, padding) {
    if (!node || typeof node.getBoundingClientRect !== "function") return false;
    const rect = node.getBoundingClientRect();
    const pad = Number.isFinite(padding) ? padding : 80;
    const target = scroller || document.scrollingElement || document.body;
    if (!target || target === document || target === document.scrollingElement || target === document.body || target === document.documentElement) {
      return rect.bottom >= -pad && rect.top <= (window.innerHeight || document.documentElement.clientHeight || 0) + pad;
    }
    const viewport = typeof target.getBoundingClientRect === "function" ? target.getBoundingClientRect() : null;
    if (!viewport) return rect.bottom >= -pad && rect.top <= (window.innerHeight || 0) + pad;
    const winHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    if (viewport.height > winHeight * 1.25 || target.scrollHeight <= target.clientHeight + 80) {
      return rect.bottom >= -pad && rect.top <= winHeight + pad;
    }
    return rect.bottom >= viewport.top - pad && rect.top <= viewport.bottom + pad;
  }

  function scrollCommentPanelTo(scroller, top) {
    const target = scroller || document.scrollingElement || document.body;
    if (target === document.scrollingElement || target === document.body || target === document.documentElement) {
      window.scrollTo(window.scrollX, top);
    } else {
      target.scrollTop = top;
    }
  }

  function getScrollTop(scroller) {
    const target = scroller || document.scrollingElement || document.body;
    if (target === document.scrollingElement || target === document.body || target === document.documentElement) {
      return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
    }
    return target.scrollTop || 0;
  }

  function attachCommentDomRefs(comment, row, anchor) {
    if (!comment) return;
    Object.defineProperty(comment, "_row", { value: row, enumerable: false, configurable: true, writable: true });
    Object.defineProperty(comment, "_profileAnchor", { value: anchor, enumerable: false, configurable: true, writable: true });
  }

  function normalizeCommentMatchText(value) {
    return cleanCommentText(value).replace(/\s+/g, "").slice(0, 120);
  }

  async function openProfileInNewTab(user, post, sourceType, comment, prelocatedLink) {
    const profileUrl = user.profile_url || "";
    if (!profileUrl) return false;
    const key = userKey(user);
    const isCommentProfile = sourceType === "comment";
    const initialLink = isCommentProfile ? null : (prelocatedLink || findProfileAnchor(profileUrl, user.user_id, comment));
    if (!isCommentProfile && !initialLink) {
      const label = sourceType === "post_author" ? "视频作者头像主页入口" : "当前评论行的主页链接";
      await progress("profiles", `未找到${label}，跳过：${user.username || key}`);
      return false;
    }
    const maxAttempts = 3;
    for (let attempt = 1; attempt <= maxAttempts && !stopped; attempt += 1) {
      const requestId = `douyin-profile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      try {
        await closeProfileTabsBeforeNext();
        const verified = isCommentProfile ? verifyCommentProfileTarget(user, comment) : null;
        const activeLink = isCommentProfile
          ? (verified && verified.ok ? verified.anchor : (prelocatedLink || null))
          : (attempt === 1 ? initialLink : findProfileAnchor(profileUrl, user.user_id, comment));
        if (!activeLink && !(isCommentProfile && verified && verified.ok)) {
          const reason = verified && verified.reason ? `: ${verified.reason}` : "";
          throw new Error(`profile link missing before click${reason}`);
        }
        await sendRuntime({ type: MSG.EXPECT_PROFILE, requestId, profileUrl, user, sourceType, comment }, 5000);
        await waitProfileOpenInterval();
        if (sourceType === "post_author") {
          await withTimeout(openPostAuthorProfileTab(activeLink, profileUrl, user, requestId), 15000, "open author profile timeout");
        } else {
          await progress("profiles", `按顺序点击评论者主页 ${attempt}/${maxAttempts}：${user.username || key}`);
          await withTimeout(openCommentProfileTab(activeLink, profileUrl, user, requestId, attempt, maxAttempts), 10000, "open comment profile timeout");
        }
        const verify = await sendRuntime({
          type: MSG.VERIFY_PROFILE_TAB,
          requestId,
          profileUrl,
          user,
          sourceType,
          timeoutMs: PROFILE_TAB_OPEN_TIMEOUT_MS
        }, PROFILE_TAB_OPEN_TIMEOUT_MS + 2500);
        if (!verify || !verify.ok || !verify.tabId) {
          throw new Error((verify && verify.error) || "profile_tab_not_opened");
        }
        await progress("profiles", `profile tab bound: tab=${verify.tabId} user=${user.username || key}`);
        const waitMs = sourceType === "comment" ? 35000 : 32000;
        const resp = await sendRuntime({
          type: MSG.WAIT_PROFILE,
          requestId,
          tabId: verify.tabId,
          profileUrl,
          user,
          post: { post_id: post.post_id, post_url: post.url, post_title: post.title },
          sourceType,
          comment,
          timeoutMs: waitMs
        }, waitMs + 6000);
        if (resp && resp.ok) {
          await closeProfileTabsBeforeNext();
          return true;
        }
        await progress("profiles", `profile not fully opened/collected: ${user.username || key} - ${(resp && resp.error) || "timeout"}`);
        await closeProfileTabsBeforeNext();
      } catch (error) {
        if (shouldCloseAfterProfileOpenError(error)) {
          await sleep(PROFILE_OPEN_FAIL_CLOSE_DELAY_MS);
          await closeProfileTabsBeforeNext();
        }
        await progress("profiles", `profile skipped/error: ${user.username || key} - ${errText(error)}`);
      }
    }
    await closeProfileTabsBeforeNext();
    await progress("profiles", `主页打开/采集连续失败 ${maxAttempts} 次，跳过该用户；页面状态：${formatPageAnalysis(analyzeCurrentPage())}；用户：${user.username || key}`);
    return false;
  }

  async function closeProfileTabsBeforeNext() {
    await sendRuntime({ type: MSG.CLOSE_PROFILE_TABS }, 5000).catch(() => null);
    await sleep(250);
  }

  function shouldCloseAfterProfileOpenError(error) {
    const reason = errText(error);
    return /profile_tab_not_opened|profile_tab_not_found|open_profile_tab_failed|open (author|comment) profile timeout|author card profile target missing/i.test(reason);
  }

  async function waitProfileOpenInterval() {
    const elapsed = Date.now() - lastProfileOpenAt;
    if (elapsed < PROFILE_OPEN_INTERVAL_MS) {
      await sleep(PROFILE_OPEN_INTERVAL_MS - elapsed);
    }
    lastProfileOpenAt = Date.now();
  }

  async function openCommentProfileTab(anchor, profileUrl, user, requestId, attempt, maxAttempts) {
    await progress("profiles", `click comment avatar/profile link ${attempt}/${maxAttempts}: ${user.username || userKey(user) || profileUrl}`);
    if (attempt === 1 && anchor && isConnectedNode(anchor)) {
      await clickProfileAnchorInNewTab(anchor, user, requestId, { forceClick: true });
      await sleep(PROFILE_CLICK_SETTLE_MS);
      return true;
    }
    await progress("profiles", `comment avatar click fallback by url ${attempt}/${maxAttempts}: ${user.username || userKey(user) || profileUrl}`);
    await openProfileUrlByBackground(profileUrl, user || {}, requestId);
    return true;
  }

  async function clickProfileAnchorInNewTab(link, user, requestId, options = {}) {
    const profileUrl = absUrl(link && (link.getAttribute("href") || link.href) || "");
    if (/douyin\.com\/user\//i.test(profileUrl) && !options.forceClick) {
      await openProfileUrlByBackground(profileUrl, user || {}, requestId);
      return;
    }
    link.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(150);
    const oldTarget = link.getAttribute("target");
    const oldRel = link.getAttribute("rel");
    try {
      link.setAttribute("target", "_blank");
      const rel = String(oldRel || "")
        .split(/\s+/)
        .filter((value) => value && !/^(noopener|noreferrer)$/i.test(value));
      link.setAttribute("rel", rel.concat("opener").join(" "));
      clickAnchorLikeUser(link, { ctrlKey: true });
      await sleep(120);
    } finally {
      if (oldTarget == null) link.removeAttribute("target");
      else link.setAttribute("target", oldTarget);
      if (oldRel == null) link.removeAttribute("rel");
      else link.setAttribute("rel", oldRel);
    }
  }

  async function openPostAuthorProfileTab(avatarLink, profileUrl, user, requestId) {
    await progress("profiles", "视频作者主页点击 1/2：点击作者头像");
    avatarLink.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(150);
    simulateClick(avatarLink);
    const cardTarget = await waitFor(
      () => findAuthorCardProfileTarget(profileUrl, user),
      PROFILE_TAB_OPEN_TIMEOUT_MS,
      "author card profile target missing"
    ).catch(() => null);
    if (cardTarget) {
      await progress("profiles", "视频作者主页点击 2/2：点击作者卡片用户名区域");
      await clickAuthorCardProfileTarget(cardTarget, profileUrl, user, requestId);
      return true;
    }
    throw new Error("author card profile target missing");
  }

  async function clickAuthorCardProfileTarget(cardTarget, profileUrl, user, requestId) {
    const anchor = findNestedOrClosestProfileAnchor(cardTarget, profileUrl, user && user.user_id);
    if (anchor) {
      await clickProfileAnchorInNewTab(anchor, user, requestId);
      return;
    }
    if (/douyin\.com\/user\//i.test(profileUrl || "")) {
      await openProfileUrlByBackground(profileUrl, user || {}, requestId);
      return;
    }
    cardTarget.scrollIntoView({ block: "center", behavior: "auto" });
    await sleep(150);
    simulateClick(cardTarget);
    await sleep(180);
  }

  function findAuthorCardProfileTarget(profileUrl, user) {
    const targets = Array.from(document.querySelectorAll(".author-card-user-name, [class*='author-card-user-name']"))
      .filter((node) => node instanceof HTMLElement && isVisible(node));
    if (!targets.length) return null;
    const id = user && (user.user_id || extractUserId(profileUrl));
    const username = cleanInlineText(user && user.username || "");
    return targets.find((node) => {
      const anchor = findNestedOrClosestProfileAnchor(node, profileUrl, id);
      if (anchor) return true;
      const value = cleanInlineText(text(node)).replace(/^@\s*/, "");
      return username ? value.includes(username) || username.includes(value) : true;
    }) || targets[0];
  }

  function findNestedOrClosestProfileAnchor(node, profileUrl, userId) {
    if (!node) return null;
    const id = userId || extractUserId(profileUrl);
    const candidates = []
      .concat(node.matches && node.matches('a[href*="/user/"]') ? [node] : [])
      .concat(Array.from(node.querySelectorAll ? node.querySelectorAll('a[href*="/user/"]') : []))
      .concat(node.closest ? [node.closest('a[href*="/user/"]')].filter(Boolean) : []);
    return candidates.find((a) => id && (a.getAttribute("href") || "").includes(id) && isVisible(a)) ||
      candidates.find((a) => canonical(absUrl(a.getAttribute("href") || a.href || "")) === canonical(profileUrl) && isVisible(a)) ||
      candidates.find((a) => isVisible(a)) ||
      null;
  }

  async function openProfileUrlByBackground(profileUrl, user, requestId) {
    const resp = await sendRuntime({ type: MSG.OPEN_PROFILE_TAB, requestId, profileUrl, user }, 12000);
    if (!resp || !resp.ok) throw new Error((resp && resp.error) || "open_profile_tab_failed");
    return true;
  }

  async function collectCurrentProfile() {
    if (profileResultSent) return;
    await waitForProfileReady(PROFILE_CONTENT_READY_TIMEOUT_MS).catch(() => undefined);
    if (profileResultSent) return;
    profileResultSent = true;
    const user = collectProfileData();
    if (!user.profile_url) user.profile_url = location.href;
    if (!user.user_id) user.user_id = extractUserId(location.href);
    if (hasProfilePayload(user)) {
      user.profile_collection_status = "complete";
      user.profile_collected_at = new Date().toISOString();
    } else {
      user.profile_collection_status = "incomplete";
      user.profile_collection_error = "profile page opened but profile content was not ready";
    }
    await sendRuntime({ type: MSG.PROFILE_RESULT, profileUrl: user.profile_url, user });
  }

  function collectProfileData() {
    const root = document;
    const username = pickProfileUsername(root);
    const account = pickProfileAccount(root);
    const bio = pickProfileBio(root, username, account);
    const stats = collectStatsText();
    return {
      platform: "douyin",
      username,
      account,
      account_raw: account,
      user_id: extractUserId(location.href),
      profile_url: location.href,
      avatar_url: pickAvatar(root),
      bio,
      stats_text: stats,
      following_count_text: findStatText(stats, "关注"),
      follower_count_text: findStatText(stats, "粉丝"),
      liked_collect_count_text: findStatText(stats, "获赞") || findStatText(stats, "喜欢"),
      note_count_text: findStatText(stats, "作品"),
      history_posts: collectProfilePosts(),
      profile_collected_at: ""
    };
  }

  async function waitForProfileReady(timeoutMs) {
    return waitFor(() => hasProfilePayload(collectProfileData()), timeoutMs, "profile content not ready");
  }

  function hasProfilePayload(user) {
    return Boolean(
      user &&
      (
        cleanInlineText(user.username || "") ||
        cleanInlineText(user.account || "") ||
        cleanInlineText(user.bio || "") ||
        (Array.isArray(user.stats_text) && user.stats_text.length) ||
        (Array.isArray(user.history_posts) && user.history_posts.length)
      )
    );
  }

  function collectProfilePosts() {
    const rows = [];
    for (const item of Array.from(document.querySelectorAll('a[href*="/video/"], a[href*="/note/"]')).slice(0, 80)) {
      const url = absUrl(item.getAttribute("href") || item.href || "");
      const postId = extractPostId(url);
      if (!postId || rows.some((row) => row.post_id === postId)) continue;
      const container = findCardContainer(item);
      rows.push({
        post_id: postId,
        title: pickTitleText(container, item, text(container || item)),
        url,
        cover_url: pickImage(container || item),
        like_count_text: pickMetricText(container || item, /赞|喜欢|like/i),
        published_at_text: pickTimeText(container || item),
        duration: pickDurationText(container || item),
        content_type: pickSearchCardMeta(container || item).content_type,
        collected_at: new Date().toISOString()
      });
    }
    return rows.slice(0, 30);
  }

  function collectStatsText() {
    const pageText = cleanInlineText(text(document.body || document));
    const extracted = ["关注", "粉丝", "获赞", "喜欢", "作品"]
      .map((label) => extractProfileStat(pageText, label))
      .filter(Boolean);
    return unique(extracted.concat(Array.from(document.querySelectorAll("span, div"))
      .map((el) => text(el))
      .filter((v) => /关注|粉丝|获赞|喜欢|作品/.test(v) && v.length < 80)))
      .slice(0, 20);
  }

  function pickProfileUsername(root) {
    const selectors = [
      '[data-e2e*="user-title"]',
      '[data-e2e*="user-name"]',
      '[class*="nickname"]',
      '[class*="user"][class*="name"]',
      "h1",
      "h2"
    ];
    for (const selector of selectors) {
      const value = text(root.querySelector(selector));
      if (value && value.length <= 80 && !/关注|粉丝|获赞|作品|抖音号/.test(value)) return value.replace(/^@\s*/, "");
    }
    return "";
  }

  function pickProfileAccount(root) {
    const values = [text(root)].concat(Array.from(root.querySelectorAll("span, div, p")).map((node) => text(node)));
    for (const value of values) {
      const match = String(value || "").match(/(?:抖音号|Douyin ID|ID)\s*[:：]?\s*([A-Za-z0-9_.-]{3,40})/i);
      if (match && match[1] && !/^(IP|关注|粉丝|获赞|作品)$/i.test(match[1])) return match[1].trim();
    }
    return "";
  }

  function pickProfileBio(root, username, account) {
    const selectors = [
      '[data-e2e*="signature"]',
      '[data-e2e*="desc"]',
      '[class*="signature"]',
      '[class*="user"][class*="desc"]',
      '[class*="desc"]'
    ];
    for (const selector of selectors) {
      const value = text(root.querySelector(selector));
      if (value && value.length <= 500 && !/关注|粉丝|获赞|作品/.test(value.slice(0, 80))) return value;
    }
    return pickProfileBioFallback(root, username, account);
  }

  function pickProfileBioFallback(root, username, account) {
    const skip = new Set([cleanInlineText(username), cleanInlineText(account)].filter(Boolean));
    const values = Array.from(root.querySelectorAll ? root.querySelectorAll("span, div, p") : [])
      .filter((node) => node instanceof HTMLElement && isVisible(node))
      .map((node) => cleanInlineText(text(node)))
      .filter((value) => value && value.length >= 4 && value.length <= 220)
      .filter((value) => !skip.has(value.replace(/^@\s*/, "")))
      .filter((value) => !looksLikeProfileNoise(value));
    return unique(values).sort((a, b) => b.length - a.length)[0] || "";
  }

  function looksLikeProfileNoise(value) {
    const v = String(value || "").trim();
    if (!v) return true;
    if (/^@?[\w.-]{3,40}$/.test(v)) return true;
    if (/^\d+(?:\.\d+)?[wWkK]?$/.test(v)) return true;
    if (/Douyin ID|ID[:：]|关注|粉丝|获赞|喜欢|作品|私信|已关注|分享|收藏|主页|橱窗|群聊|更多|搜索|直播|shop|message|follow|followers|following|likes|posts/i.test(v)) return true;
    return false;
  }

  function findStatText(stats, label) {
    return extractProfileStat(cleanInlineText((stats || []).join(" ")), label) || "";
  }

  function extractProfileStat(value, label) {
    const raw = String(value || "");
    if (!raw || !label) return "";
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const number = "([0-9][0-9,.]*(?:万|千|w|W|k|K)?)";
    const after = raw.match(new RegExp(`${escaped}\\s*${number}`));
    if (after) return `${after[1]} ${label}`;
    const before = raw.match(new RegExp(`${number}\\s*${escaped}`));
    if (before) return `${before[1]} ${label}`;
    return "";
  }

  async function closePostDetail(beforeUrl) {
    const close = Array.from(document.querySelectorAll('[aria-label*="关闭"], [class*="close"], button'))
      .find((node) => isVisible(node) && /关闭|close|×|返回/.test(text(node) || node.getAttribute("aria-label") || ""));
    if (close) {
      simulateClick(close);
      await sleep(900);
      return;
    }
    if (beforeUrl && canonical(location.href) !== canonical(beforeUrl)) {
      history.back();
      await sleep(1200);
      return;
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", bubbles: true }));
    await sleep(900);
  }

  function analyzeCurrentPage() {
    const detailRoot = findDetailRoot();
    const panel = findCommentPanelRoot(detailRoot, { skipRows: false });
    const rows = panel ? findCommentRows(panel) : [];
    return {
      url: location.href,
      isSearch: findVisualSearchCardRoots().length > 0,
      isDetail: /douyin\.com\/(?:video|note)\//i.test(location.href) || Boolean(findDetailActionBar()),
      isProfile: isDouyinProfilePage(),
      hasPostUrl: /douyin\.com\/(?:video|note)\//i.test(location.href),
      hasActionBar: Boolean(findDetailActionBar()),
      hasAuthor: Boolean(findVideoAuthorAnchor(detailRoot || document)),
      hasMedia: Boolean(document.querySelector("video, picture, canvas, img[src]")),
      hasCommentPanel: hasOpenedCommentPanel(panel, detailRoot),
      hasCommentEnd: hasCommentEndMarker(panel || document),
      commentRows: rows.length,
      searchCards: findVisualSearchCardRoots().length
    };
  }

  function formatPageAnalysis(snapshot) {
    const s = snapshot || analyzeCurrentPage();
    const parts = [];
    if (s.isSearch) parts.push(`结果页卡片=${s.searchCards}`);
    if (s.isDetail) parts.push("详情页");
    if (s.isProfile) parts.push("用户主页");
    if (s.hasActionBar) parts.push("有操作栏");
    if (s.hasAuthor) parts.push("有作者");
    if (s.hasMedia) parts.push("有媒体");
    if (s.hasCommentPanel) parts.push(`评论区=${s.commentRows}`);
    if (s.hasCommentEnd) parts.push("评论到底");
    if (!parts.length) parts.push("未知页面");
    return parts.join("，");
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
    if (comment && comment._profileAnchor && isVisible(comment._profileAnchor) && anchorMatchesProfile(comment._profileAnchor, profileUrl, id)) {
      return comment._profileAnchor;
    }
    const scope = comment && comment._row && isVisible(comment._row)
      ? comment._row
      : (comment && comment.comment_id
        ? findCommentRows(findCommentPanelRoot() || document).find((node) => {
            const link = findAuthorLink(node);
            const rowContent = normalizeCommentMatchText(pickCommentContent(node, text(link).replace(/^@\s*/, "")));
            const expectedContent = normalizeCommentMatchText(comment.content || "");
            return link && anchorMatchesProfile(link, profileUrl, id) && expectedContent && rowContent &&
              (rowContent.includes(expectedContent) || expectedContent.includes(rowContent));
          })
        : null);
    if (scope) {
      const scopedLinks = Array.from(scope.querySelectorAll('a[href*="/user/"]'));
      const visibleScopedLinks = scopedLinks.filter((a) => isVisible(a));
      const scoped = visibleScopedLinks.find((a) => id && (a.getAttribute("href") || "").includes(id)) ||
        visibleScopedLinks.find((a) => canonical(absUrl(a.getAttribute("href") || a.href || "")) === canonical(profileUrl)) ||
        (unique(visibleScopedLinks.map((a) => canonical(absUrl(a.getAttribute("href") || a.href || "")))).length === 1 ? visibleScopedLinks[0] : null);
      if (scoped) return scoped;
    }
    if (comment && comment.comment_id) return null;
    const links = Array.from(document.querySelectorAll('a[href*="/user/"]'));
    return links.find((a) => id && (a.getAttribute("href") || "").includes(id) && isVisible(a)) ||
      links.find((a) => canonical(absUrl(a.getAttribute("href") || a.href || "")) === canonical(profileUrl) && isVisible(a)) ||
      null;
  }

  function anchorMatchesProfile(anchor, profileUrl, userId) {
    if (!anchor) return false;
    const raw = anchor.getAttribute("href") || anchor.href || "";
    return Boolean((userId && raw.includes(userId)) || canonical(absUrl(raw)) === canonical(profileUrl));
  }

  function findPostClickTarget(postId, postUrl, card) {
    if (card && card._waterfallId) {
      const waterfallItem = document.getElementById(card._waterfallId);
      const visualTarget = waterfallItem && findVisualPostClickTarget(waterfallItem);
      if (visualTarget) return visualTarget;
    }
    const links = Array.from(document.querySelectorAll('a[href*="/video/"], a[href*="/note/"]'));
    const explicit = links.find((a) => postId && (a.getAttribute("href") || "").includes(postId) && isVisible(a)) ||
      links.find((a) => canonical(absUrl(a.getAttribute("href") || a.href || "")) === canonical(postUrl) && isVisible(a)) ||
      null;
    if (explicit) return explicit;
    if (card && card._clickTarget && isVisible(card._clickTarget)) return card._clickTarget;
    if (postId) {
      const waterfallItem = document.getElementById(`waterfall_item_${postId}`);
      const visualTarget = waterfallItem && findVisualPostClickTarget(waterfallItem);
      if (visualTarget) return visualTarget;
    }
    return null;
  }

  function findVisualSearchCardRoots() {
    const roots = [];
    const seenRoots = new Set();
    const addRoot = (node) => {
      if (!node || seenRoots.has(node)) return;
      seenRoots.add(node);
      roots.push(node);
    };
    findDouyinSearchCardRoots().forEach(addRoot);
    findVisibleMediaCardRoots().forEach(addRoot);
    const selectors = [
      '[data-e2e*="search"] li',
      '[data-e2e*="search"] article',
      '[data-e2e*="search"] section',
      '[data-e2e*="search"] div',
      'main li',
      'main article',
      'main section',
      'main div',
      'li',
      'article',
      'section',
      'div'
    ];
    const seen = new Set();
    for (const selector of selectors) {
      for (const node of Array.from(document.querySelectorAll(selector))) {
        if (seen.has(node)) continue;
        seen.add(node);
        if (looksLikeVisualSearchCard(node)) addRoot(node);
      }
    }
    return roots
      .filter((node) => !roots.some((other) => other !== node && node.contains(other) && cardArea(other) < cardArea(node) * 0.85))
      .sort(sortByPosition);
  }

  function findVisibleMediaCardRoots() {
    const seen = new Set();
    const cards = [];
    const mediaNodes = Array.from(document.querySelectorAll("img[src], video, canvas, picture"))
      .filter((node) => node instanceof HTMLElement && isVisible(node))
      .sort(sortByPosition);
    for (const media of mediaNodes) {
      const mediaRect = media.getBoundingClientRect();
      if (mediaRect.top < 160 || mediaRect.width < 90 || mediaRect.height < 90) continue;
      const card = findMediaCardRoot(media);
      if (!card || seen.has(card) || !looksLikeVisualSearchCard(card)) continue;
      seen.add(card);
      cards.push(card);
    }
    return cards
      .filter((node) => !cards.some((other) => other !== node && node.contains(other) && cardArea(other) < cardArea(node) * 0.9))
      .sort(sortByPosition);
  }

  function findMediaCardRoot(media) {
    let best = null;
    let node = media;
    for (let i = 0; i < 10 && node && node !== document.body; i += 1) {
      const rect = node.getBoundingClientRect();
      const value = text(node);
      const cardSized = rect.width >= 150 && rect.width <= 380 && rect.height >= 180 && rect.height <= 760;
      const hasCardText = /@\s*\S|·\s*|图文|\d{1,2}:\d{2}|#\S+|月\d{1,2}日|\d{4}年|天前|小时前|分钟前/.test(value);
      const isNoise = /相关搜索|问问AI|筛选|通知|私信|投稿/.test(value.slice(0, 120));
      if (cardSized && hasCardText && !isNoise) best = node;
      node = node.parentElement;
    }
    return best;
  }

  function debugSearchCardCounts() {
    try {
      const exact = findDouyinSearchCardRoots().length;
      const media = findVisibleMediaCardRoots().length;
      const visual = findVisualSearchCardRoots().length;
      const imgs = Array.from(document.querySelectorAll("img[src]")).filter((node) => node instanceof HTMLElement && isVisible(node)).length;
      return `debug exact=${exact} media=${media} visual=${visual} visibleImgs=${imgs}`;
    } catch (error) {
      return `debug failed=${errText(error)}`;
    }
  }

  function findDouyinSearchCardRoots() {
    return Array.from(document.querySelectorAll('#waterFallScrollContainer .AMqhOzPC[id^="waterfall_item_"]'))
      .filter(looksLikeDouyinWaterfallItem)
      .sort(sortByPosition);
  }

  function looksLikeDouyinWaterfallItem(node) {
    if (!node || !isVisible(node)) return false;
    const id = String(node.id || "");
    if (!/^waterfall_item_\d+/.test(id)) return false;
    const card = node.querySelector(".search-result-card");
    if (!card || card.querySelector(".TLxYU_vw, .KtbMeylm")) return false;
    return Boolean(card.querySelector(".videoImage, .LFQCShEn, img, [style*='background-image']"));
  }

  function looksLikeVisualSearchCard(node) {
    if (!node || !node.querySelectorAll || !isVisible(node)) return false;
    if (looksLikeDouyinWaterfallItem(node)) return true;
    const rect = node.getBoundingClientRect();
    if (rect.top < 170 || rect.left < -20 || rect.width < 80 || rect.width > 620 || rect.height < 45 || rect.height > 760) return false;
    const mediaCount = node.querySelectorAll("video, canvas, picture, img").length;
    if (mediaCount > 12) return false;
    const value = text(node);
    if (value.length < 20 || value.length > 1400) return false;
    if (/相关搜索|问问AI|综合|筛选|客户端|通知|私信/.test(value.slice(0, 120))) return false;
    const hasAuthorOrTime = /@\s*\S|·\s*|分钟前|小时前|天前|刚刚|\d{1,2}月\d{1,2}日|\d{4}年/.test(value);
    const hasPostMarker = /图文|\d{1,2}:\d{2}|#\S+/.test(value);
    return hasAuthorOrTime && (hasPostMarker || value.length > 40);
  }

  function findVisualPostClickTarget(card) {
    if (!card) return null;
    const link = card.querySelector('a[href*="/video/"], a[href*="/note/"]');
    if (link && isVisible(link)) return link;
    const targets = [
      card.querySelector(".videoImage"),
      card.querySelector(".LFQCShEn"),
      card.querySelector(".search-result-card"),
      card.querySelector("video"),
      card.querySelector("canvas"),
      card.querySelector("picture"),
      card.querySelector("img"),
      card.querySelector('[role="button"]'),
      card.querySelector("[tabindex]"),
      card
    ].filter(Boolean);
    return targets.find((target) => {
      if (!isVisible(target)) return false;
      const rect = target.getBoundingClientRect();
      return rect.width >= 40 && rect.height >= 40;
    }) || null;
  }

  function findVisualAuthorNode(card) {
    const exact = card.querySelector(".ZZUGohYq, .WldPmwm5");
    if (exact && isVisible(exact)) return exact;
    const nodes = Array.from(card.querySelectorAll("a, span, div"))
      .filter((node) => isVisible(node))
      .filter((node) => /^@\s*\S+/.test(text(node)) || text(node).length <= 40);
    return nodes.find((node) => /^@\s*\S+/.test(text(node))) || null;
  }

  function pickSearchCardMeta(card) {
    const duration = pickDurationText(card);
    const typeText = text(card && card.querySelector && card.querySelector(".TtoFOFHo, .A2phXnfo, [class*='badge']"));
    const published = pickSearchPublishedAt(card);
    return {
      content_type: typeText || (duration ? "视频" : ""),
      duration,
      published_at_text: published
    };
  }

  function pickSearchPublishedAt(card) {
    const exact = text(card && card.querySelector && card.querySelector(".Dp8LSWfW, .dO8W7uoF, .video-create-time .time"));
    if (exact) return exact.replace(/^·\s*/, "").trim();
    return pickTimeText(card).replace(/^·\s*/, "").trim();
  }

  function pickDurationText(root) {
    const exact = text(root && root.querySelector && root.querySelector(".FnM1bbIQ"));
    if (/^\d{1,2}:\d{2}(?::\d{2})?$/.test(exact)) return exact;
    const values = Array.from(root && root.querySelectorAll ? root.querySelectorAll("span, div") : [])
      .map((node) => text(node))
      .filter((value) => /^\d{1,2}:\d{2}(?::\d{2})?$/.test(value));
    return values[0] || "";
  }

  function pickAwemeId(root, infoRoot, postUrl) {
    const fromModal = extractModalPostId(postUrl) || extractModalPostId(location.href);
    if (fromModal) return fromModal;
    const nodes = [root, infoRoot].filter(Boolean);
    for (const node of nodes) {
      const attrs = [
        node.getAttribute && node.getAttribute("data-e2e-vid"),
        node.getAttribute && node.getAttribute("data-e2e-aweme-id"),
        node.dataset && node.dataset.e2eVid,
        node.dataset && node.dataset.e2eAwemeId
      ];
      const found = attrs.find((value) => /^\d{8,}$/.test(String(value || "")));
      if (found) return String(found);
      const child = node.querySelector && node.querySelector("[data-e2e-vid], [data-e2e-aweme-id]");
      const childValue = child && (child.getAttribute("data-e2e-vid") || child.getAttribute("data-e2e-aweme-id"));
      if (/^\d{8,}$/.test(String(childValue || ""))) return String(childValue);
    }
    return extractPostId(postUrl);
  }

  function pickDetailCreateTime(infoRoot) {
    const exact = text(infoRoot && infoRoot.querySelector && infoRoot.querySelector(".video-create-time .time, .time"));
    return exact ? exact.replace(/^·\s*/, "").trim() : "";
  }

  function pickDetailContentType(infoRoot, root, card) {
    const exact = text(infoRoot && infoRoot.querySelector && infoRoot.querySelector(".account-card, .A2phXnfo, [class*='account-card']"));
    if (exact) return exact;
    if (card && card.content_type) return card.content_type;
    if (pickDurationText(root) || (root && root.querySelector && root.querySelector("video"))) return "视频";
    return "";
  }

  function pickPostUrl(card) {
    const nodes = [card].concat(Array.from(card.querySelectorAll ? card.querySelectorAll("[href], [data-url], [data-href], [data-link]") : []));
    for (const node of nodes) {
      const raw = node.getAttribute && (node.getAttribute("href") || node.getAttribute("data-url") || node.getAttribute("data-href") || node.getAttribute("data-link"));
      const url = absUrl(raw || "");
      if (/douyin\.com\/(?:video|note)\//i.test(url)) return url;
    }
    return postUrlFromId(extractWaterfallPostId(card));
  }

  function cardArea(node) {
    if (!node || typeof node.getBoundingClientRect !== "function") return 0;
    const rect = node.getBoundingClientRect();
    return Math.max(0, rect.width) * Math.max(0, rect.height);
  }

  function sortByPosition(a, b) {
    const ar = a && typeof a.getBoundingClientRect === "function" ? a.getBoundingClientRect() : { top: 0, left: 0 };
    const br = b && typeof b.getBoundingClientRect === "function" ? b.getBoundingClientRect() : { top: 0, left: 0 };
    return (ar.top - br.top) || (ar.left - br.left);
  }

  function extractWaterfallPostId(node) {
    const m = String(node && node.id || "").match(/^waterfall_item_(\d+)/);
    return m ? m[1] : "";
  }

  function findAuthorLink(root) {
    if (!root) return null;
    const avatarLinks = Array.from(root.querySelectorAll ? root.querySelectorAll('.comment-item-avatar a[href*="/user/"], [class*="comment-item-avatar"] a[href*="/user/"]') : []);
    const avatarLink = avatarLinks.find((a) => isVisible(a) && !/\/video\/|\/note\//i.test(a.getAttribute("href") || ""));
    if (avatarLink) return avatarLink;
    const links = Array.from(root.querySelectorAll ? root.querySelectorAll('a[href*="/user/"]') : []);
    return links.find((a) => isVisible(a) && !/\/video\/|\/note\//i.test(a.getAttribute("href") || "")) || null;
  }

  function findActiveDetailRoot() {
    const selectors = [
      '#slidelist [data-e2e="feed-active-video"]',
      '[data-e2e="feed-active-video"]',
      '#slidelist [data-e2e="feed-item"]',
      '#slidelist .dySwiperSlide'
    ];
    for (const selector of selectors) {
      const nodes = Array.from(document.querySelectorAll(selector))
        .filter((node) => node instanceof HTMLElement && isVisible(node))
        .filter((node) => node.querySelector('[data-e2e="video-info"], [data-e2e="feed-comment-icon"], [data-e2e="video-player-digg"], video, img[src]'));
      if (nodes.length) return nodes[0];
    }
    return null;
  }

  function findVideoInfoRoot(scope) {
    const root = scope && scope.querySelectorAll ? scope : document;
    return root.querySelector('[data-e2e="video-info"], #video-info-wrap [data-e2e-aweme-id], #video-info-wrap .video-info-detail') ||
      document.querySelector('[data-e2e="video-info"], #video-info-wrap [data-e2e-aweme-id], #video-info-wrap .video-info-detail');
  }

  function findDetailRoot() {
    const active = findActiveDetailRoot();
    if (active) return active;
    const info = findVideoInfoRoot(document);
    if (info) {
      const slide = info.closest('[data-e2e="feed-active-video"], [data-e2e="feed-item"], .dySwiperSlide, [slot="inside"]');
      return slide || info.closest("section, article, main, div") || document;
    }
    const actionBar = findDetailActionBar();
    if (!actionBar) return document;
    let node = actionBar.parentElement;
    for (let i = 0; i < 8 && node && node !== document.body; i += 1) {
      if (node.querySelector("video, picture, canvas, [data-e2e='video-info']")) return node;
      node = node.parentElement;
    }
    return document;
  }

  function findDetailActionBar() {
    const root = findActiveDetailRoot() || document;
    const selector = '[data-e2e="feed-comment-icon"], [data-e2e="video-player-digg"], [data-e2e="video-player-collect"], [data-e2e="video-player-share"]';
    const anchor = Array.from(root.querySelectorAll ? root.querySelectorAll(selector) : [])
      .find((node) => node instanceof HTMLElement && isVisible(node)) ||
      Array.from(document.querySelectorAll(selector))
        .find((node) => node instanceof HTMLElement && isVisible(node));
    if (!anchor) return null;
    let node = anchor;
    for (let i = 0; i < 8 && node && node !== document.body; i += 1) {
      if (node.querySelector('[data-e2e="feed-comment-icon"]') && node.querySelector('[data-e2e="video-player-digg"]')) return node;
      node = node.parentElement;
    }
    return anchor.parentElement || anchor;
  }

  function findVideoAuthorAnchor(scope) {
    const root = scope && scope.querySelectorAll ? scope : (findActiveDetailRoot() || document);
    const exact = root.querySelector('a[data-e2e="video-avatar"][href*="/user/"]') ||
      document.querySelector('a[data-e2e="video-avatar"][href*="/user/"]');
    if (exact && isVisible(exact)) return exact;
    const actionBar = findDetailActionBar();
    if (!actionBar) return null;
    return Array.from(actionBar.querySelectorAll('a[href*="/user/"]')).find((a) => isVisible(a)) || null;
  }

  function pickDetailAuthorName(root, infoRoot, card, authorAnchor, desc) {
    const fromDesc = String(desc || "").match(/@([^·\n#]{2,80})\s*[·]/);
    const candidates = [
      card && card.author_username,
      fromDesc && fromDesc[1],
      text((infoRoot || root || document).querySelector('.author-card-user-name, [class*="author"][class*="user-name"], [class*="author"][class*="name"]')),
      text(authorAnchor)
    ];
    for (const value of candidates) {
      const clean = cleanInlineText(value).replace(/^@\s*/, "");
      if (!clean || clean.length > 80) continue;
      if (/前往|访问|主页|西瓜视频|tooltip/i.test(clean)) continue;
      return clean;
    }
    return "";
  }

  function findCommentOpenButton(scope) {
    const roots = getCommentSearchRoots(scope);
    for (const root of roots) {
      const exact = Array.from(root.querySelectorAll ? root.querySelectorAll('[data-e2e="feed-comment-icon"]') : [])
        .filter((node) => node instanceof HTMLElement && isVisible(node) && !isInsideOpenedCommentPanel(node))
        .sort(sortByPosition)[0];
      if (exact) return normalizeCommentOpenButton(exact, root);
    }
    for (const root of roots) {
      const fallback = Array.from(root.querySelectorAll ? root.querySelectorAll('[data-e2e*="comment"], button, div[role="button"], [tabindex]') : [])
        .filter((node) => node instanceof HTMLElement && isVisible(node) && !isInsideOpenedCommentPanel(node))
        .find((node) => /评论|comment/i.test(text(node) || node.getAttribute("aria-label") || ""));
      if (fallback) return normalizeCommentOpenButton(fallback, root);
    }
    return null;
  }

  function getCommentSearchRoots(scope) {
    return uniqueNodes([
      scope && scope.querySelectorAll ? scope : null,
      findDetailActionBar(),
      findActiveDetailRoot(),
      findDetailRoot(),
      document
    ].filter(Boolean));
  }

  function normalizeCommentOpenButton(node, root) {
    if (!node || !(node instanceof HTMLElement)) return node;
    if (node.matches('[data-e2e="feed-comment-icon"]')) return node;
    const holder = node.closest('[data-e2e="feed-comment-icon"]');
    if (holder && (!root || root === document || root.contains(holder))) return holder;
    const clickable = node.closest('button, [role="button"], [tabindex]');
    if (clickable && (!root || root === document || root.contains(clickable))) return clickable;
    return node;
  }

  function isInsideOpenedCommentPanel(node) {
    const panel = findCommentPanelRoot(null, { skipRows: true });
    return Boolean(panel && node && (panel === node || panel.contains(node)));
  }

  function isCommentEndMarkerText(value) {
    return /暂时没有更多评论|没有更多评论|no more comments/i.test(String(value || ""));
  }

  function hasCommentEndMarker(scope) {
    const root = scope && scope.querySelectorAll ? scope : findCommentPanelRoot() || document;
    const exact = root.querySelector && root.querySelector(".fanRMYie");
    if (exact && isVisible(exact) && isCommentEndMarkerText(text(exact))) return true;
    return Array.from(root.querySelectorAll ? root.querySelectorAll("div, span, p") : [])
      .some((node) => node instanceof HTMLElement && isVisible(node) && isCommentEndMarkerText(text(node)));
  }

  function findCommentPanelRoot(scope, options) {
    const opts = options || {};
    const roots = getCommentSearchRoots(scope);
    for (const root of roots) {
      const exactList = root.querySelector && root.querySelector('[data-e2e="comment-list"]');
      if (exactList && isVisible(exactList) && !isInDetailActionBar(exactList)) return exactList;
    }
    if (!opts.skipRows) {
      for (const root of roots) {
        const rows = findCommentRows(root).slice(0, 6);
        if (!rows.length) continue;
        const scroller = closestScrollable(rows[0]);
        if (scroller && !isInDetailActionBar(scroller)) return scroller;
        const panel = rows[0].closest('aside, section, [class*="comment"], [data-e2e*="comment"], div');
        if (panel && !isInDetailActionBar(panel)) return panel;
      }
    }
    for (const root of roots) {
      const candidates = Array.from(root.querySelectorAll ? root.querySelectorAll('aside, section, [class*="comment"], [data-e2e*="comment"], div') : [])
        .filter((node) => node instanceof HTMLElement && isVisible(node) && !isInDetailActionBar(node));
      const panel = candidates.find((node) => {
        const value = text(node).slice(0, 260);
        if (!/评论|comment/i.test(value) && !isCommentEndMarkerText(value)) return false;
        if (isCommentEndMarkerText(value)) return true;
        return node.querySelector('a[href*="/user/"]') || node.scrollHeight > node.clientHeight + 120;
      });
      if (panel) return panel;
    }
    return null;
  }

  function hasOpenedCommentPanel(panel, scope) {
    if (!panel || isInDetailActionBar(panel)) return false;
    const button = findCommentOpenButton(scope);
    if (button && panel.contains(button)) return false;
    if (findCommentRows(panel).length > 0) return true;
    if (hasCommentEndMarker(panel)) return true;
    if (panel.matches && panel.matches('[data-e2e="comment-list"]')) return true;
    const value = text(panel).slice(0, 260);
    return /评论|comment/i.test(value) && panel.scrollHeight > panel.clientHeight + 120;
  }

  function findCommentRows(scope) {
    const root = scope && scope.querySelectorAll ? scope : document;
    const exactItems = Array.from(root.querySelectorAll('[data-e2e="comment-item"]'))
      .filter((item) => item instanceof HTMLElement && isVisible(item) && !isInDetailActionBar(item) && !isInSearchCard(item))
      .filter((item) => item.querySelector('a[href*="/user/"]'));
    if (exactItems.length) return exactItems.sort(sortByPosition);
    const videoAuthor = findVideoAuthorAnchor();
    const videoAuthorUrl = root === document && videoAuthor
      ? canonical(absUrl(videoAuthor.getAttribute("href") || videoAuthor.href || ""))
      : "";
    const links = Array.from(root.querySelectorAll('a[href*="/user/"]'))
      .filter((link) => {
        if (!isVisible(link) || link.matches('[data-e2e="video-avatar"], [data-e2e="video-avatar"] *') || isInDetailActionBar(link)) return false;
        if (videoAuthorUrl && canonical(absUrl(link.getAttribute("href") || link.href || "")) === videoAuthorUrl) return false;
        return true;
      });
    const seen = new Set();
    const rows = [];
    for (const link of links) {
      const row = findCommentRowRoot(link);
      if (!row || seen.has(row) || !looksLikeCommentRow(row, link)) continue;
      seen.add(row);
      rows.push(row);
    }
    return rows.sort(sortByPosition);
  }

  function findCommentRowRoot(link) {
    let best = null;
    let node = link;
    for (let i = 0; i < 7 && node && node !== document.body; i += 1) {
      const value = text(node);
      const rect = node.getBoundingClientRect();
      const hasUser = Boolean(node.querySelector('a[href*="/user/"]'));
      const compactEnough = value.length >= 2 && value.length <= 900;
      const rowSized = rect.width >= 160 && rect.height >= 24 && rect.height <= 320;
      if (hasUser && compactEnough && rowSized && !isInDetailActionBar(node) && !isInSearchCard(node)) best = node;
      node = node.parentElement;
    }
    return best || link.closest('li, article, section, div');
  }

  function looksLikeCommentRow(row, link) {
    if (!row || !isVisible(row) || isInDetailActionBar(row) || isInSearchCard(row)) return false;
    const value = text(row);
    if (!value || value.length < 2 || value.length > 900) return false;
    if (/关注|粉丝|作品|获赞|私信|分享|收藏/.test(value.slice(0, 80))) return false;
    const authorName = text(link);
    const content = pickCommentContent(row, authorName);
    return Boolean(content && content.length >= 2);
  }

  function pickCommentContent(row, authorName) {
    const author = String(authorName || "").trim();
    const exact = row.querySelector && row.querySelector(".LvAtyU_f, [data-e2e*='comment-content'], [class*='comment-content']");
    const exactValue = cleanCommentText(textWithImageAlt(exact).replace(author, ""));
    if (exactValue && !isCommentNoiseText(exactValue)) return exactValue.slice(0, 500);
    const candidates = Array.from(row.querySelectorAll('span, p, div'))
      .filter((node) => node instanceof HTMLElement && isVisible(node) && !node.querySelector('a[href*="/user/"]'))
      .map((node) => textWithImageAlt(node))
      .filter((value) => value && value.length >= 2 && value.length <= 300)
      .map((value) => cleanCommentText(value.replace(author, "")))
      .filter((value) => value && !isCommentNoiseText(value));
    if (candidates.length) {
      return candidates.sort((a, b) => b.length - a.length)[0].slice(0, 500);
    }
    return cleanCommentText(text(row).replace(author, "")).slice(0, 500);
  }

  function pickCommentUsername(row, author) {
    const direct = cleanInlineText(text(author).replace(/^@\s*/, ""));
    if (isUsefulUsername(direct)) return direct;
    const img = author && author.querySelector && author.querySelector("img");
    const imgName = cleanInlineText((img && (img.getAttribute("alt") || img.getAttribute("title") || img.getAttribute("aria-label"))) || "").replace(/^@\s*/, "");
    if (isUsefulUsername(imgName)) return imgName;
    const anchors = Array.from(row.querySelectorAll ? row.querySelectorAll('a[href*="/user/"]') : [])
      .filter((node) => isVisible(node))
      .sort(sortByPosition);
    for (const link of anchors) {
      const value = cleanInlineText(text(link).replace(/^@\s*/, ""));
      if (isUsefulUsername(value)) return value;
    }
    const values = Array.from(row.querySelectorAll ? row.querySelectorAll("span, div, p") : [])
      .filter((node) => node instanceof HTMLElement && isVisible(node) && !node.querySelector('a[href*="/user/"]'))
      .sort(sortByPosition)
      .map((node) => cleanInlineText(text(node).replace(/^@\s*/, "")))
      .filter(isUsefulUsername);
    return values[0] || "";
  }

  function isUsefulUsername(value) {
    const v = String(value || "").trim();
    if (!v || v.length < 1 || v.length > 80) return false;
    if (looksLikeMetricCount(v) || isCommentNoiseText(v)) return false;
    if (/IP|回复|点赞|评论|分享|展开|收起|查看|更多|刚刚|昨天|分钟前|小时前|天前|reply|like|comment/i.test(v)) return false;
    return true;
  }

  function textWithImageAlt(node) {
    if (!node) return "";
    const parts = [];
    const walk = (current) => {
      if (!current) return;
      if (current.nodeType === Node.TEXT_NODE) {
        parts.push(current.nodeValue || "");
        return;
      }
      if (current.nodeType !== Node.ELEMENT_NODE) return;
      const el = current;
      if (el.tagName === "IMG") {
        const alt = el.getAttribute("alt") || "";
        if (alt) parts.push(alt);
        return;
      }
      for (const child of Array.from(el.childNodes || [])) walk(child);
    };
    walk(node);
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  function isCommentNoiseText(value) {
    const v = String(value || "").trim();
    if (!v) return true;
    if (looksLikeMetricCount(v)) return true;
    if (/^(评论|点赞|回复|分享|收藏|展开|收起|查看更多|更多回复|全部回复)$/.test(v)) return true;
    if (/^(刚刚|昨天|\d+\s*(秒|分钟|小时|天)前|\d{1,2}-\d{1,2}|\d{4}-\d{1,2}-\d{1,2})$/.test(v)) return true;
    if (/^IP属地/.test(v)) return true;
    return false;
  }

  function pickCommentId(row) {
    let node = row;
    for (let i = 0; i < 4 && node && node !== document.body; i += 1) {
      const id = node.getAttribute && (node.getAttribute("data-id") || node.getAttribute("data-comment-id") || node.id);
      if (id && !/comment-icon|comment-button/i.test(id)) return id;
      node = node.parentElement;
    }
    return "";
  }

  function pickActionMetric(selector) {
    const node = document.querySelector(selector);
    if (!node) return "";
    const values = Array.from(node.querySelectorAll("span, div"))
      .map((item) => text(item))
      .filter((value) => value && value.length < 40);
    return values.find(looksLikeMetricCount) || values.find((value) => !/^(赞|喜欢|评论|收藏|分享)$/.test(value)) || "";
  }

  function pickCompactText(node) {
    const value = text(node);
    return value && value.length < 40 ? value : "";
  }

  function pickLocationText(root) {
    const values = Array.from(root.querySelectorAll ? root.querySelectorAll("span, div") : [])
      .map((node) => text(node))
      .filter((value) => /^IP属地|IP：|来自/.test(value) && value.length < 40);
    if (values[0]) return values[0].replace(/^IP属地[:：]?|^IP[:：]?|^来自/, "").trim();
    return pickCommentMeta(root).location || "";
  }

  function pickCommentMeta(row) {
    const raw = text(row && row.querySelector && row.querySelector(".GOkWHE6S, [class*='comment'][class*='time'], [class*='time']"));
    return splitTimeLocation(raw);
  }

  function splitTimeLocation(value) {
    const raw = String(value || "").replace(/^·\s*/, "").trim();
    if (!raw) return { published_at_text: "", location: "" };
    const parts = raw.split("·").map((part) => part.trim()).filter(Boolean);
    if (parts.length >= 2) return { published_at_text: parts[0], location: parts.slice(1).join("·") };
    return { published_at_text: raw, location: "" };
  }

  function pickCommentLikeText(row) {
    const exact = text(row && row.querySelector && row.querySelector(".comment-item-stats-container .wiQmZrKV span, .wiQmZrKV span"));
    return looksLikeMetricCount(exact) ? exact : "";
  }

  function parseMetricNumber(value) {
    const raw = String(value || "").replace(/,/g, "").trim();
    const match = raw.match(/(\d+(?:\.\d+)?)(\s*万|\s*w|\s*k)?/i);
    if (!match) return null;
    const n = Number(match[1]);
    if (!Number.isFinite(n)) return null;
    const unit = String(match[2] || "").trim().toLowerCase();
    if (unit === "万" || unit === "w") return Math.round(n * 10000);
    if (unit === "k") return Math.round(n * 1000);
    return Math.round(n);
  }

  function looksLikeMetricCount(value) {
    const raw = String(value || "").trim();
    return /^(\d+(?:\.\d+)?)(万|w|W|k|K)?$/.test(raw);
  }

  function closestScrollable(node) {
    let current = node;
    for (let i = 0; i < 8 && current && current !== document.body; i += 1) {
      if (current.scrollHeight > current.clientHeight + 120) return current;
      current = current.parentElement;
    }
    return null;
  }

  function isInDetailActionBar(node) {
    const actionBar = findDetailActionBar();
    return Boolean(actionBar && node && (actionBar === node || actionBar.contains(node)));
  }

  function isInSearchCard(node) {
    return Boolean(node && node.closest && node.closest('#waterFallScrollContainer .AMqhOzPC, .search-result-card'));
  }

  function uniqueNodes(nodes) {
    const seen = new Set();
    return nodes.filter((node) => {
      if (!node || seen.has(node)) return false;
      seen.add(node);
      return true;
    });
  }

  function findCardContainer(link) {
    let node = link;
    for (let i = 0; i < 8 && node && node !== document.body; i += 1) {
      if (node.querySelectorAll && node.querySelectorAll('a[href*="/video/"], a[href*="/note/"]').length >= 1 && text(node).length > 15) {
        return node;
      }
      node = node.parentElement;
    }
    return link.closest("li, article, section, div") || link;
  }

  function findCommentScroller() {
    const root = arguments.length ? arguments[0] : null;
    const base = root && root.querySelectorAll ? root : document;
    const nodes = uniqueNodes([base].concat(Array.from(base.querySelectorAll('[class*="comment"], [data-e2e*="comment"], aside, section, div'))));
    return nodes.find((node) => {
      if (!node || !isVisible(node) || isInDetailActionBar(node)) return false;
      if (node.scrollHeight <= node.clientHeight + 120) return false;
      const value = text(node).slice(0, 260);
      return /评论|comment/i.test(value) || findCommentRows(node).length > 0;
    }) || null;
  }

  function pickTitleText(card, link, fallback) {
    const candidates = [
      card && card.querySelector(".d1M9CJkV"),
      card && card.querySelector(".BjLsdJMi"),
      card && card.querySelector('[class*="title"]'),
      card && card.querySelector('[class*="desc"]'),
      link
    ].filter(Boolean);
    for (const node of candidates) {
      const value = text(node);
      if (value && value.length > 1 && value.length < 300) return value;
    }
    return String(fallback || "").slice(0, 260);
  }

  function pickDescriptionText(root, fallback) {
    const actionBar = findDetailActionBar();
    const commentPanel = findCommentPanelRoot();
    const candidates = Array.from(root.querySelectorAll('.d1M9CJkV, .BjLsdJMi, [data-e2e*="desc"], [data-e2e*="title"], [class*="title"], [class*="desc"], h1, h2, p, span, div'))
      .filter((node) => node instanceof HTMLElement && isVisible(node))
      .filter((node) => !isInSearchCard(node) && !(actionBar && actionBar.contains(node)) && !(commentPanel && commentPanel.contains(node)))
      .map((node) => text(node))
      .filter((value) => value && value.length > 5 && value.length < 500)
      .filter((value) => !/评论|转发|点赞|收藏|关注|分享|举报|不感兴趣/.test(value));
    return candidates[0] || fallback || "";
  }

  function pickMetricText(root, pattern) {
    if (!root || !root.querySelectorAll) return "";
    const values = Array.from(root.querySelectorAll(".MwR2AYaY span, .pMq55q1M span, span, div, button"))
      .map((node) => text(node))
      .filter((value) => value && value.length < 40);
    return values.find((value) => looksLikeMetricCount(value)) || values.find((value) => pattern.test(value)) || "";
  }

  function pickTimeText(root) {
    const values = Array.from(root.querySelectorAll ? root.querySelectorAll(".Dp8LSWfW, .dO8W7uoF, span, div") : [])
      .map((node) => text(node))
      .filter((value) => /刚刚|秒前|分钟前|小时前|昨天|天前|周前|月前|年前|\d{1,2}-\d{1,2}|\d{4}|\d{1,2}月\d{1,2}日/.test(value) && value.length < 40);
    const meta = values[0] ? splitTimeLocation(values[0]) : null;
    return meta ? meta.published_at_text : "";
  }

  function pickImage(root) {
    const img = root && root.querySelector && root.querySelector('img.fnWBjiik[src], img.s3hRValp[src], img[src]');
    return img ? img.src : "";
  }

  function pickCoverImage(root) {
    const exact = root && root.querySelector && root.querySelector('img.fnWBjiik[src], img[elementtiming="lcp_ele"][src], .backgroundCover img[src], img[class*="cover"][src]');
    if (exact) return exact.src;
    return pickImage(root) || pickCssBackgroundImage(root);
  }

  function collectImageUrls(root) {
    if (!root || !root.querySelectorAll) return [];
    const urls = Array.from(root.querySelectorAll("img[src]"))
      .filter((img) => img instanceof HTMLImageElement && isVisible(img))
      .map((img) => img.currentSrc || img.src)
      .filter((url) => url && !/avatar|emoji|twemoji|tos-cn-i-tsj2vxp0zn/i.test(url));
    const bg = pickCssBackgroundImage(root);
    return unique(bg ? urls.concat(bg) : urls).slice(0, 20);
  }

  function pickMediaUrl(root) {
    const video = root && root.querySelector && root.querySelector("video");
    return video ? (video.currentSrc || video.src || "") : "";
  }

  function collectMediaUrls(root) {
    if (!root || !root.querySelectorAll) return [];
    const urls = [];
    for (const video of Array.from(root.querySelectorAll("video"))) {
      const direct = video.currentSrc || video.src || "";
      if (direct) urls.push(direct);
      for (const source of Array.from(video.querySelectorAll("source[src]"))) {
        urls.push(source.src);
      }
    }
    return unique(urls).slice(0, 12);
  }

  function pickCssBackgroundImage(root) {
    if (!root || !root.querySelectorAll) return "";
    const nodes = [root].concat(Array.from(root.querySelectorAll("[style*='background-image']")));
    for (const node of nodes) {
      const style = node instanceof HTMLElement ? getComputedStyle(node).backgroundImage || "" : "";
      const match = style.match(/url\(["']?([^"')]+)["']?\)/);
      if (match && match[1]) return absUrl(match[1]);
    }
    return "";
  }

  function pickAvatar(root) {
    const img = root && root.querySelector && (
      root.querySelector('[data-e2e="live-avatar"] img[src]') ||
      root.querySelector('img[class*="avatar"][src]') ||
      root.querySelector('img[src*="avatar"]') ||
      root.querySelector('img[src]')
    );
    return img ? img.src : "";
  }

  function cleanCommentText(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .replace(/回复|点赞|评论|分享|展开|收起|查看更多|更多回复|全部回复/g, " ")
      .trim();
  }

  function cleanInlineText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function inferCommentDepth(item, scope) {
    const cls = String(item.className || "");
    if (/reply|sub|children|child|二级/.test(cls)) return 1;
    if (scope && scope.getBoundingClientRect) {
      const left = item.getBoundingClientRect().left - scope.getBoundingClientRect().left;
      if (left > 56) return 1;
    }
    return 0;
  }

  function isDouyinProfilePage() {
    return /douyin\.com\/user\//i.test(location.href);
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
      .replace(/抖音|搜索|_.*$/g, " ")
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
    return String(url || "").split("#")[0].split("?")[0].replace(/\/$/, "");
  }

  function extractPostId(url) {
    const m = String(url || "").match(/\/(?:video|note)\/([^/?#]+)/i);
    return m ? m[1] : "";
  }

  function extractModalPostId(url) {
    try {
      const parsed = new URL(String(url || ""), location.origin);
      const value = parsed.searchParams.get("modal_id") || parsed.searchParams.get("aweme_id") || parsed.searchParams.get("item_id") || "";
      return /^\d{8,}$/.test(value) ? value : "";
    } catch (_) {
      const m = String(url || "").match(/[?&](?:modal_id|aweme_id|item_id)=(\d{8,})/);
      return m ? m[1] : "";
    }
  }

  function postUrlFromId(postId) {
    const id = String(postId || "").trim();
    if (!/^[A-Za-z0-9_-]{8,}$/.test(id) || /^local/i.test(id)) return "";
    return `https://www.douyin.com/video/${id}`;
  }

  function extractUserId(url) {
    const m = String(url || "").match(/\/user\/([^/?#]+)/i);
    return m ? m[1] : "";
  }

  function isVisible(el) {
    if (!el) return false;
    if (typeof el.getBoundingClientRect !== "function") return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean)));
  }

  function hashText(value) {
    let hash = 0;
    const textValue = String(value || "");
    for (let i = 0; i < textValue.length; i += 1) {
      hash = ((hash << 5) - hash + textValue.charCodeAt(i)) | 0;
    }
    return Math.abs(hash).toString(16);
  }

  function simulateClick(el) {
    if (!el) throw new Error("click target missing");
    if (typeof el.getBoundingClientRect !== "function" || typeof el.dispatchEvent !== "function") {
      console.warn(TAG, "skip invalid click target", el);
      return;
    }
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

  function clickAnchorLikeUser(anchor, options = {}) {
    if (!anchor || typeof anchor.click !== "function") {
      simulateClick(anchor);
      return;
    }
    if (typeof anchor.getBoundingClientRect === "function" && typeof anchor.dispatchEvent === "function") {
      const rect = anchor.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      for (const type of ["pointerover", "pointermove", "pointerdown", "mousedown", "pointerup", "mouseup"]) {
        const eventInit = {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: x,
          clientY: y,
          button: 0,
          buttons: type.includes("down") ? 1 : 0,
          ctrlKey: Boolean(options.ctrlKey),
          metaKey: Boolean(options.metaKey)
        };
        if (type.startsWith("pointer")) {
          anchor.dispatchEvent(new PointerEvent(type, Object.assign({}, eventInit, { pointerId: 1, pointerType: "mouse", isPrimary: true })));
        } else {
          anchor.dispatchEvent(new MouseEvent(type, eventInit));
        }
      }
    }
    anchor.click();
  }

  function waitFor(fn, timeoutMs, errorMessage) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
      const tick = () => {
        if (stopped) return reject(new Error("stopped"));
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

  async function attemptAction(label, action, options) {
    const opts = options || {};
    const maxAttempts = clamp(opts.maxAttempts, 1, 3, 3);
    const phase = opts.phase || "posts";
    let lastError = null;
    for (let attempt = 1; attempt <= maxAttempts && !stopped; attempt += 1) {
      try {
        if (attempt > 1) await progress(phase, `${label} 重试 ${attempt}/${maxAttempts}`);
        const result = await action(attempt);
        if (opts.requireTruthy && !result) throw new Error(`${label} returned empty result`);
        return result;
      } catch (error) {
        lastError = error;
        await progress(phase, `${label} 失败 ${attempt}/${maxAttempts}：${errText(error)}`);
        if (attempt < maxAttempts) await sleep(500);
      }
    }
    const message = `${label} 连续失败 ${maxAttempts} 次，跳过当前动作；页面状态：${formatPageAnalysis(analyzeCurrentPage())}；原因：${errText(lastError)}`;
    await progress(phase, message);
    if (opts.throwOnFail === false) return null;
    throw new Error(message);
  }

  function reportError(error) {
    console.warn(TAG, error);
    return sendRuntime({ type: MSG.ERROR, error: errText(error) });
  }

  function sendRuntime(payload, timeoutMs) {
    return new Promise((resolve) => {
      let done = false;
      const timer = setTimeout(() => {
        if (done) return;
        done = true;
        resolve({ ok: false, error: "runtime_message_timeout" });
      }, runtimeMessageTimeout(payload, timeoutMs));
      try {
        chrome.runtime.sendMessage(payload, (response) => {
          if (done) return;
          done = true;
          clearTimeout(timer);
          if (chrome.runtime.lastError) return resolve({ ok: false, error: chrome.runtime.lastError.message });
          resolve(response || { ok: true });
        });
      } catch (error) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve({ ok: false, error: errText(error) });
      }
    });
  }

  function runtimeMessageTimeout(payload, overrideMs) {
    if (Number.isFinite(Number(overrideMs))) return Math.max(1000, Number(overrideMs));
    const type = payload && payload.type;
    if (type === MSG.WAIT_PROFILE) return clamp(Number(payload.timeoutMs || 0) + 5000, 8000, 70000, 20000);
    if (type === MSG.PROGRESS || type === MSG.CLOSE_PROFILE_TABS) return 5000;
    if (type === MSG.POST_DONE || type === MSG.PROFILE_RESULT || type === MSG.DONE || type === MSG.ERROR) return 10000;
    return 12000;
  }

  function withTimeout(promise, timeoutMs, label) {
    return Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error(label || "timeout")), timeoutMs))
    ]);
  }

  function normalizeSettings(input) {
    return {
      limitMode: input.limitMode === "videos" ? "videos" : "profiles",
      keyword: String(input.keyword || "").trim(),
      maxPosts: clamp(input.maxPosts, 1, 200, 10),
      profileLimit: clamp(input.profileLimit, 1, 300, 20)
    };
  }

  function canOpenMoreProfiles(profileCount, opts) {
    return opts.limitMode !== "profiles" || profileCount < opts.profileLimit;
  }

  function profileTargetReached(profileCount, opts) {
    return opts.limitMode === "profiles" && profileCount >= opts.profileLimit;
  }

  function targetReached(profileCount, processedPosts, opts) {
    if (opts.limitMode === "videos") return processedPosts >= opts.maxPosts;
    return profileCount >= opts.profileLimit;
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
