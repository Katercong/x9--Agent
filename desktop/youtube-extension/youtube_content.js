(() => {
  if (globalThis.__X9_YOUTUBE_CONTENT_LOADED__) return;
  globalThis.__X9_YOUTUBE_CONTENT_LOADED__ = true;

  const MSG = {
    PING: "X9_YOUTUBE_PING",
    STOP: "X9_YOUTUBE_STOP",
    COLLECT: "X9_YOUTUBE_COLLECT",
    COLLECT_SEARCH: "X9_YOUTUBE_COLLECT_SEARCH",
    COLLECT_PROFILE: "X9_YOUTUBE_COLLECT_PROFILE",
    COLLECT_CHANNEL_VIDEOS: "X9_YOUTUBE_COLLECT_CHANNEL_VIDEOS",
    SUBMIT_SEARCH: "X9_YOUTUBE_SUBMIT_SEARCH"
  };

  let stopped = false;
  let running = false;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || typeof message.type !== "string") return false;
    if (message.type === MSG.PING) {
      sendResponse({ ok: true, href: location.href, page_kind: detectPageKind() });
      return true;
    }
    if (message.type === MSG.STOP) {
      stopped = true;
      running = false;
      sendResponse({ ok: true });
      return true;
    }
    if (message.type === MSG.SUBMIT_SEARCH) {
      submitHomeSearch(message.keyword || "")
        .then((result) => sendResponse({ ok: true, result }))
        .catch((error) => sendResponse({ ok: false, error: errorText(error) }));
      return true;
    }
    if (message.type === MSG.COLLECT_SEARCH) {
      collectSearchPage(message.settings || {})
        .then((result) => sendResponse({ ok: true, result }))
        .catch((error) => sendResponse({ ok: false, error: errorText(error) }));
      return true;
    }
    if (message.type === MSG.COLLECT_PROFILE) {
      collectProfilePage(message.settings || {})
        .then((result) => sendResponse({ ok: true, result }))
        .catch((error) => sendResponse({ ok: false, error: errorText(error) }));
      return true;
    }
    if (message.type === MSG.COLLECT_CHANNEL_VIDEOS) {
      collectChannelVideos(message.settings || {})
        .then((result) => sendResponse({ ok: true, result }))
        .catch((error) => sendResponse({ ok: false, error: errorText(error) }));
      return true;
    }
    if (message.type === MSG.COLLECT) {
      collectYoutubeVideoPage(message.settings || {})
        .then((result) => sendResponse({ ok: true, result }))
        .catch((error) => sendResponse({ ok: false, error: errorText(error) }));
      return true;
    }
    return false;
  });

  async function submitHomeSearch(keyword) {
    const value = String(keyword || "").trim();
    if (!value) throw new Error("keyword_required");
    const input = document.querySelector("input#search, input[name='search_query']");
    if (!input) return { submitted: false, reason: "search_input_not_found" };
    setInputValue(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const button = document.querySelector("button#search-icon-legacy, ytd-searchbox button, button[aria-label='Search']");
    if (button) safeClick(button);
    else input.form?.submit?.();
    await sleep(500);
    return { submitted: true };
  }

  async function collectSearchPage(settings) {
    stopped = false;
    const opts = normalizeSettings(settings);
    const videos = new Map();
    let stableRounds = 0;
    let lastCount = 0;

    for (let round = 0; round <= opts.searchScrollRounds && !stopped; round += 1) {
      for (const video of collectVisibleSearchVideos()) {
        if (!videos.has(video.video_url)) videos.set(video.video_url, video);
        if (videos.size >= opts.maxVideos) break;
      }
      if (videos.size >= opts.maxVideos) break;
      if (videos.size === lastCount) stableRounds += 1;
      else {
        stableRounds = 0;
        lastCount = videos.size;
      }
      if (stableRounds >= 4) break;
      window.scrollBy({ top: 1200, left: 0, behavior: "smooth" });
      await sleep(opts.waitMs);
    }

    return {
      page_kind: "search",
      page_url: location.href,
      keyword: inferKeywordFromUrl(),
      videos: Array.from(videos.values()).slice(0, opts.maxVideos),
      collected_at: new Date().toISOString()
    };
  }

  function collectVisibleSearchVideos() {
    const containers = collectSearchResultContainers();
    const videos = [];

    for (const container of containers) {
      for (const videoLink of findVideoLinks(container)) {
        const videoUrl = utils().normalizeVideoUrl(videoLink?.href || videoLink?.getAttribute("href") || "");
        const videoId = utils().extractVideoId(videoUrl);
        if (!videoUrl || !videoId) continue;
        const contentType = utils().detectContentType(videoUrl) || "video";
        const card = closestVideoCard(videoLink) || container;
        const channelAnchor = findChannelAnchor(card) || findChannelAnchor(container);
        const channelUrl = utils().normalizeChannelUrl(channelAnchor?.href || channelAnchor?.getAttribute("href") || "");
        videos.push({
          video_id: videoId,
          video_url: videoUrl,
          content_type: contentType,
          video_title: text(videoLink) || videoLink?.getAttribute("title") || videoLink?.getAttribute("aria-label") || "",
          creator_channel_name: text(channelAnchor),
          creator_channel_url: channelUrl,
          search_result_text: truncate(text(card) || text(container), 1200),
          collected_at: new Date().toISOString()
        });
      }
    }

    return utils().dedupeBy(videos, (item) => item.video_url);
  }

  function collectSearchResultContainers() {
    const selectors = [
      "ytd-video-renderer",
      "ytd-reel-item-renderer",
      "ytd-reel-shelf-renderer",
      "ytm-shorts-lockup-view-model",
      "yt-lockup-view-model",
      "ytm-video-with-context-renderer",
      "ytd-rich-item-renderer",
      "ytd-rich-grid-media"
    ].join(",");
    const seen = new Set();
    const out = [];
    for (const root of searchResultRoots()) {
      const candidates = root.matches?.(selectors)
        ? [root, ...Array.from(root.querySelectorAll(selectors))]
        : Array.from(root.querySelectorAll(selectors));
      for (const node of candidates) {
        if (!node || seen.has(node) || !isVisible(node) || isSearchRecommendationNode(node)) continue;
        seen.add(node);
        out.push(node);
      }
    }
    return out;
  }

  function searchResultRoots() {
    const roots = [
      document.querySelector("ytd-two-column-search-results-renderer #primary #contents"),
      document.querySelector("ytd-section-list-renderer #contents"),
      document.querySelector("ytd-search ytd-section-list-renderer"),
      document.querySelector("ytd-search")
    ].filter(Boolean);
    return roots.length ? roots : [document.querySelector("main") || document.body].filter(Boolean);
  }

  function isSearchRecommendationNode(node) {
    return Boolean(node.closest?.([
      "ytd-watch-next-secondary-results-renderer",
      "ytd-compact-video-renderer",
      "#secondary",
      "#related"
    ].join(",")));
  }

  async function collectYoutubeVideoPage(settings) {
    if (running) return snapshotVideoResult(settings, "already_running");
    running = true;
    stopped = false;
    const opts = normalizeSettings(settings);

    try {
      await expandVideoDescription();
      await expandPublicText();
      if (opts.maxComments > 0) {
        await openShortsCommentsIfNeeded();
        await expandCommentReplies(opts.maxComments);
        for (let round = 0; round < opts.scrollRounds && !stopped; round += 1) {
          scrollCommentArea();
          await sleep(opts.waitMs);
          await expandCommentReplies(opts.maxComments);
          if (collectComments(opts.maxComments).length >= opts.maxComments) break;
        }
      }
      const result = snapshotVideoResult(opts, stopped ? "stopped" : "done");
      running = false;
      return result;
    } catch (error) {
      running = false;
      throw error;
    }
  }

  function snapshotVideoResult(settings, status) {
    const video = collectVideo();
    const channel = collectChannel();
    const maxComments = Number.isFinite(Number(settings.maxComments)) ? Number(settings.maxComments) : 50;
    const comments = collectComments(maxComments);
    const videoDetailText = cleanDetailText([video.description, video.visible_text_sample].filter(Boolean).join("\n"));
    const videoContacts = detector().detectContacts(videoDetailText);
    const emails = unique(videoContacts.filter((contact) => contact.type === "email").map((contact) => contact.value));
    const collectedAt = new Date().toISOString();
    return {
      ok: true,
      status,
      page_kind: "video",
      page_url: location.href,
      video: {
        ...video,
        email: emails[0] || "",
        emails,
        contacts: videoContacts,
        video_detail_text: truncate(videoDetailText, 6000)
      },
      channel,
      comments,
      counts: {
        comments: comments.length
      },
      settings,
      collected_at: collectedAt
    };
  }

  async function collectProfilePage(settings = {}) {
    if (settings.openAboutDialog !== false) {
      await openChannelAboutDialog();
    }
    await expandPublicText();
    await sleep(250);
    const profileText = collectProfileText();
    const contacts = detector().detectContacts(profileText);
    const mailtoEmails = collectMailtoEmails();
    const emailContacts = contacts.filter((contact) => contact.type === "email");
    const emails = unique([
      ...emailContacts.map((contact) => contact.value),
      ...mailtoEmails
    ].map((email) => String(email || "").toLowerCase()).filter(Boolean));
    const channelUrl = collectCurrentChannelUrl();

    return {
      page_kind: "channel_profile",
      page_url: location.href,
      channel_name: collectProfileChannelName(),
      channel_url: channelUrl,
      channel_id: utils().extractChannelId(channelUrl),
      channel_handle: utils().extractChannelHandle(channelUrl),
      email: emails[0] || "",
      emails,
      contacts,
      external_links: collectExternalLinks(),
      profile_text: truncate(profileText, 6000),
      hidden_email_button_present: collectHiddenEmailButtonPresent(),
      captcha_required: collectCaptchaRequired(profileText),
      collected_at: new Date().toISOString()
    };
  }

  async function collectChannelVideos(settings) {
    stopped = false;
    const opts = normalizeSettings(settings);
    const videos = new Map();
    for (let round = 0; round <= Math.min(6, opts.searchScrollRounds) && !stopped; round += 1) {
      for (const video of collectVisibleChannelVideos()) {
        if (!videos.has(video.video_url)) videos.set(video.video_url, video);
        if (videos.size >= 10) break;
      }
      if (videos.size) break;
      window.scrollBy({ top: 1000, left: 0, behavior: "smooth" });
      await sleep(opts.waitMs);
    }
    return {
      page_kind: "channel_videos",
      page_url: location.href,
      channel_url: collectCurrentChannelUrl(),
      videos: Array.from(videos.values()),
      collected_at: new Date().toISOString()
    };
  }

  function collectVisibleChannelVideos() {
    const containers = Array.from(document.querySelectorAll([
      "ytd-rich-item-renderer",
      "ytd-grid-video-renderer",
      "ytd-rich-grid-media",
      "ytd-reel-item-renderer",
      "ytm-shorts-lockup-view-model",
      "yt-lockup-view-model",
      "ytd-compact-video-renderer"
    ].join(",")));
    const videos = [];
    for (const container of containers) {
      const videoLink = findVideoLink(container);
      const videoUrl = utils().normalizeVideoUrl(videoLink?.href || videoLink?.getAttribute("href") || "");
      const videoId = utils().extractVideoId(videoUrl);
      if (!videoUrl || !videoId) continue;
      videos.push({
        video_id: videoId,
        video_url: videoUrl,
        content_type: utils().detectContentType(videoUrl) || "video",
        video_title: text(videoLink) || videoLink?.getAttribute("title") || videoLink?.getAttribute("aria-label") || "",
        source_text: truncate(text(container), 800),
        collected_at: new Date().toISOString()
      });
    }
    return utils().dedupeBy(videos, (item) => item.video_url);
  }

  function collectProfileText() {
    const selectors = [
      "tp-yt-paper-dialog yt-about-channel-renderer",
      "[role='dialog'] yt-about-channel-renderer",
      "yt-dialog-view-model yt-about-channel-renderer",
      "tp-yt-paper-dialog",
      "[role='dialog']",
      "yt-dialog-view-model",
      "ytd-channel-about-metadata-renderer",
      "yt-about-channel-renderer",
      "yt-description-preview-view-model",
      "yt-page-header-renderer",
      "ytd-c4-tabbed-header-renderer",
      "#description-container",
      "#links-container",
      "#channel-header-container",
      "#contentContainer"
    ];
    const parts = [];
    for (const selector of selectors) {
      for (const node of Array.from(document.querySelectorAll(selector))) {
        if (!isVisible(node)) continue;
        const value = text(node);
        if (value && !parts.includes(value)) parts.push(value);
      }
    }
    const focused = parts.join("\n").trim();
    return focused || visibleText();
  }

  function collectVideo() {
    const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href;
    const videoUrl = utils().normalizeVideoUrl(canonical || location.href) || canonical || location.href;
    const titleNode = first([
      "h1.ytd-watch-metadata yt-formatted-string",
      "h1.title yt-formatted-string",
      "yt-reel-player-header-renderer h2",
      "h1"
    ]);
    const descriptionNode = first([
      "ytd-watch-metadata #description-inline-expander",
      "ytd-text-inline-expander #content",
      "ytd-video-secondary-info-renderer #description",
      "#description",
      "yt-reel-video-description-view-model"
    ]);
    const domDescription = text(descriptionNode);
    const playerDescription = collectPlayerDescription();
    const metaDescription = meta("description");
    return {
      video_id: utils().extractVideoId(videoUrl),
      video_url: videoUrl,
      content_type: utils().detectContentType(videoUrl) || "video",
      title: text(titleNode) || meta("title") || document.title || "",
      description: longestText([domDescription, playerDescription, metaDescription]),
      visible_text_sample: collectVideoVisibleText().slice(0, 5000)
    };
  }

  function collectPlayerDescription() {
    const details = collectPlayerVideoDetails();
    if (details?.shortDescription) return String(details.shortDescription);
    return "";
  }

  function collectPlayerVideoDetails() {
    const direct = readPath(globalThis, ["ytInitialPlayerResponse", "videoDetails"]);
    if (direct && typeof direct === "object") return direct;
    for (const script of Array.from(document.scripts)) {
      const content = script.textContent || "";
      const markerIndex = content.indexOf("ytInitialPlayerResponse");
      if (markerIndex < 0) continue;
      const jsonStart = content.indexOf("{", markerIndex);
      if (jsonStart < 0) continue;
      const jsonText = extractBalancedJson(content, jsonStart);
      if (!jsonText) continue;
      try {
        const parsed = JSON.parse(jsonText);
        if (parsed?.videoDetails) return parsed.videoDetails;
      } catch {
        // Some YouTube scripts contain partial assignments; try the next script.
      }
    }
    return null;
  }

  function collectVideoVisibleText() {
    const selectors = [
      "ytd-watch-metadata",
      "ytd-video-primary-info-renderer",
      "ytd-video-secondary-info-renderer",
      "yt-reel-player-header-renderer",
      "yt-reel-video-description-view-model",
      "#above-the-fold",
      "#description-inline-expander",
      "#description"
    ];
    const parts = [];
    for (const selector of selectors) {
      for (const node of Array.from(document.querySelectorAll(selector))) {
        const value = text(node);
        if (value && !parts.includes(value)) parts.push(value);
      }
    }
    const focused = parts.join("\n").trim();
    return focused.length >= 40 ? focused : visibleText();
  }

  function collectChannel() {
    const preferredAnchor = firstAnchor([
      "ytd-video-owner-renderer a[href^='/@']",
      "ytd-video-owner-renderer a[href*='/channel/']",
      "ytd-channel-name a[href^='/@']",
      "ytd-channel-name a[href*='/channel/']",
      "yt-reel-channel-bar-view-model a[href^='/@']",
      "yt-reel-channel-bar-view-model a[href*='/channel/']"
    ]);
    const fallbackAnchor = Array.from(document.querySelectorAll("a[href]")).find((a) => {
      const href = a.getAttribute("href") || "";
      return /^\/(@|channel\/|c\/|user\/)/.test(href) && Boolean(text(a) || a.getAttribute("aria-label"));
    });
    const playerDetails = collectPlayerVideoDetails();
    const anchor = preferredAnchor || fallbackAnchor;
    const channelIdUrl = playerDetails?.channelId ? `https://www.youtube.com/channel/${playerDetails.channelId}` : "";
    const url = utils().normalizeChannelUrl(anchor?.href || anchor?.getAttribute("href") || channelIdUrl);
    return {
      channel_name: (text(anchor) || anchor?.getAttribute("aria-label") || playerDetails?.author || "").trim(),
      channel_url: url,
      channel_id: utils().extractChannelId(url),
      channel_handle: utils().extractChannelHandle(url)
    };
  }

  function collectComments(maxComments) {
    const limit = Math.max(0, Number(maxComments) || 0);
    if (!limit) return [];
    const roots = collectCommentRoots();
    const comments = [];
    const seen = new Set();

    for (const root of roots) {
      if (comments.length >= limit) break;
      if (!isVisible(root)) continue;
      const authorAnchor = findCommentAuthorAnchor(root);
      const contentNode = firstWithin(root, [
        "#content-text",
        "yt-attributed-string#content-text",
        ".comment-content",
        "[id='comment-content']"
      ]);
      const commentText = text(contentNode);
      const authorUrl = utils().normalizeChannelUrl(authorAnchor?.href || authorAnchor?.getAttribute("href") || "");
      const key = `${authorUrl}|${commentText}`;
      if (!commentText || !authorUrl || seen.has(key)) continue;
      seen.add(key);
      comments.push({
        author_name: (text(authorAnchor) || authorAnchor?.getAttribute("aria-label") || "").trim(),
        author_channel_url: authorUrl,
        comment_text: commentText,
        comment_url: absoluteUrl(firstWithin(root, ["#published-time-text a[href]", "a[href*='lc=']"])?.getAttribute("href") || ""),
        comment_index: comments.length
      });
    }

    return comments;
  }

  function collectCommentRoots() {
    const roots = Array.from(document.querySelectorAll([
      "ytd-comment-renderer",
      "ytd-comment-view-model"
    ].join(",")));
    if (roots.length) return roots;
    return Array.from(document.querySelectorAll("ytd-comment-thread-renderer"));
  }

  function findVideoLink(container) {
    return findVideoLinks(container)[0] || null;
  }

  function findVideoLinks(container) {
    const selectors = [
      "a#video-title[href*='/watch']",
      "a#video-title[href*='/shorts/']",
      "a#thumbnail[href*='/watch']",
      "a#thumbnail[href*='/shorts/']",
      "a.shortsLockupViewModelHostEndpoint[href*='/shorts/']",
      "a[href*='/shorts/'][aria-label]",
      "a[href*='/shorts/'][title]",
      "a[href*='/watch?v=']",
      "a[href*='/shorts/']"
    ];
    const seen = new Set();
    const links = [];
    for (const selector of selectors) {
      for (const link of Array.from(container.querySelectorAll(selector))) {
        const href = link.href || link.getAttribute("href") || "";
        const normalized = utils().normalizeVideoUrl(href);
        if (!normalized || seen.has(normalized)) continue;
        seen.add(normalized);
        links.push(link);
      }
    }
    return links;
  }

  function closestVideoCard(node) {
    return node?.closest?.([
      "ytd-video-renderer",
      "ytd-rich-item-renderer",
      "ytd-grid-video-renderer",
      "ytd-reel-item-renderer",
      "ytm-shorts-lockup-view-model",
      "yt-lockup-view-model",
      "ytm-video-with-context-renderer",
      "ytd-rich-grid-media"
    ].join(","));
  }

  function findChannelAnchor(container) {
    return firstWithin(container, [
      "ytd-channel-name a[href^='/@']",
      "ytd-channel-name a[href*='/channel/']",
      "a.yt-simple-endpoint[href^='/@']",
      "a[href^='/@']",
      "a[href*='/channel/']"
    ]);
  }

  function findCommentAuthorAnchor(root) {
    return firstWithin(root, [
      "#author-text[href]",
      "a#author-text",
      "a[href^='/@']",
      "a[href*='/channel/']",
      "a.yt-simple-endpoint[href]"
    ]);
  }

  function collectCurrentChannelUrl() {
    const fromLocation = utils().normalizeChannelUrl(location.href);
    if (fromLocation) return fromLocation;
    const canonical = document.querySelector('link[rel="canonical"]')?.href || "";
    return utils().normalizeChannelUrl(canonical);
  }

  function collectProfileChannelName() {
    return text(first([
      "yt-page-header-renderer h1",
      "ytd-c4-tabbed-header-renderer #channel-name",
      "#channel-header-container h1",
      "h1"
    ])) || meta("title") || document.title.replace(/ - YouTube$/i, "");
  }

  function collectMailtoEmails() {
    const emails = [];
    for (const link of Array.from(document.querySelectorAll("a[href^='mailto:']"))) {
      if (!isVisible(link)) continue;
      const raw = (link.getAttribute("href") || "").replace(/^mailto:/i, "").split("?")[0];
      if (raw && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw)) emails.push(raw);
    }
    return unique(emails);
  }

  function collectHiddenEmailButtonPresent() {
    return Array.from(document.querySelectorAll("button, a, [role='button'], tp-yt-paper-button"))
      .some((node) => isVisible(node) && isHiddenEmailTrigger(triggerLabel(node)));
  }

  function collectCaptchaRequired(profileText) {
    const pageText = String(profileText || "").toLowerCase();
    const captchaNodes = Array.from(document.querySelectorAll(".g-recaptcha, iframe[src*='recaptcha'], iframe[title*='reCAPTCHA'], textarea#g-recaptcha-response"));
    if (captchaNodes.some((node) => isVisible(node))) {
      return true;
    }
    return pageText.includes("recaptcha")
      || pageText.includes("i'm not a robot")
      || pageText.includes("i am not a robot")
      || pageText.includes("\u6211\u4e0d\u662f\u673a\u5668\u4eba");
  }

  function collectExternalLinks() {
    return unique(Array.from(document.querySelectorAll("a[href]"))
      .filter((link) => isVisible(link))
      .map((link) => absoluteUrl(link.getAttribute("href") || ""))
      .filter((url) => url && !/youtube\.com/i.test(url))
      .slice(0, 100));
  }

  async function openChannelAboutDialog() {
    if (!utils().normalizeChannelUrl(location.href)) return;
    if (hasChannelAboutDialog()) return;

    const candidates = Array.from(document.querySelectorAll([
      "yt-page-header-renderer button",
      "yt-page-header-view-model button",
      "yt-page-header-renderer [role='button']",
      "yt-page-header-view-model [role='button']",
      "ytd-c4-tabbed-header-renderer button",
      "#channel-header-container button",
      "#page-header button",
      "button",
      "[role='button']"
    ].join(",")));

    const ranked = candidates
      .filter((node) => isVisible(node) && isAboutDialogTrigger(node))
      .sort((a, b) => triggerScore(b) - triggerScore(a));

    for (const node of ranked.slice(0, 8)) {
      node.scrollIntoView?.({ block: "center", inline: "nearest" });
      await sleep(120);
      safeClick(node);
      await sleep(600);
      if (hasChannelAboutDialog()) return;
    }
  }

  function hasChannelAboutDialog() {
    return Boolean(Array.from(document.querySelectorAll("tp-yt-paper-dialog, [role='dialog'], yt-dialog-view-model"))
      .find((node) => {
        if (!isVisible(node)) return false;
        const value = text(node).toLowerCase();
        return value.includes("view email address")
          || value.includes("\u67e5\u770b\u7535\u5b50\u90ae\u4ef6\u5730\u5740")
          || value.includes("more info")
          || value.includes("\u66f4\u591a\u4fe1\u606f")
          || value.includes("description")
          || value.includes("\u8bf4\u660e");
      }));
  }

  function isAboutDialogTrigger(node) {
    const label = triggerLabel(node);
    if (!label || isHiddenEmailTrigger(label)) return false;
    if (label === "more" || label === "\u66f4\u591a") return isInsideChannelHeader(node);
    return label.includes("about")
      || label.includes("description")
      || label.includes("more info")
      || label.includes("\u7b80\u4ecb")
      || label.includes("\u8bf4\u660e")
      || label.includes("\u66f4\u591a\u4fe1\u606f");
  }

  function triggerScore(node) {
    const label = triggerLabel(node);
    let score = isInsideChannelHeader(node) ? 10 : 0;
    if (label.includes("\u7b80\u4ecb") || label.includes("about")) score += 5;
    if (label.includes("\u66f4\u591a\u4fe1\u606f") || label.includes("more info")) score += 4;
    if (label === "\u66f4\u591a" || label === "more") score += 2;
    return score;
  }

  function triggerLabel(node) {
    return `${node.getAttribute("aria-label") || ""} ${node.getAttribute("title") || ""} ${node.textContent || ""}`
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function isHiddenEmailTrigger(label) {
    return label.includes("view email address")
      || label.includes("show email")
      || label.includes("business email")
      || label.includes("\u67e5\u770b\u7535\u5b50\u90ae\u4ef6\u5730\u5740")
      || label.includes("\u67e5\u770b\u90ae\u7bb1")
      || label.includes("\u5546\u52a1\u90ae\u7bb1");
  }

  function isInsideChannelHeader(node) {
    return Boolean(node.closest?.([
      "yt-page-header-renderer",
      "yt-page-header-view-model",
      "ytd-c4-tabbed-header-renderer",
      "#channel-header-container",
      "#page-header"
    ].join(",")));
  }

  async function expandVideoDescription() {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const targets = Array.from(document.querySelectorAll([
        "ytd-watch-metadata #description-inline-expander #expand",
        "ytd-watch-metadata #description-inline-expander tp-yt-paper-button#expand",
        "ytd-watch-metadata ytd-text-inline-expander #expand",
        "ytd-watch-metadata tp-yt-paper-button#expand",
        "#description-inline-expander #expand",
        "ytd-text-inline-expander #expand"
      ].join(","))).filter(Boolean);
      let clicked = false;
      for (const target of targets) {
        if (!isVisible(target)) continue;
        target.scrollIntoView?.({ block: "center", inline: "nearest" });
        await sleep(120);
        safeClick(target);
        clicked = true;
        await sleep(350);
      }
      if (!clicked || !document.querySelector("#description-inline-expander #expand, ytd-text-inline-expander #expand")) return;
    }
  }

  async function expandPublicText() {
    const buttons = Array.from(document.querySelectorAll("button, tp-yt-paper-button, yt-button-shape button"));
    for (const button of buttons) {
      const label = (button.getAttribute("aria-label") || button.textContent || "").trim().toLowerCase();
      if (label === "more" || label === "show more" || label.includes("\u66f4\u591a") || label.includes("\u5c55\u5f00")) {
        safeClick(button);
        await sleep(250);
      }
    }
  }

  async function openShortsCommentsIfNeeded() {
    if (!/\/shorts\//i.test(location.pathname)) return;
    if (document.querySelector("ytd-comment-thread-renderer, ytd-comment-view-model")) return;
    const target = Array.from(document.querySelectorAll("button, ytd-button-renderer, yt-button-shape button")).find((button) => {
      const label = `${button.getAttribute("aria-label") || ""} ${button.textContent || ""}`.toLowerCase();
      return label.includes("comment") || label.includes("\u8bc4\u8bba");
    });
    if (target) {
      safeClick(target);
      await sleep(1200);
    }
  }

  async function expandCommentReplies(maxComments) {
    const maxClicks = Math.max(1, Math.min(12, Number(maxComments) || 12));
    const candidates = Array.from(document.querySelectorAll("button, yt-button-shape button, tp-yt-paper-button, [role='button']"))
      .filter((button) => isVisible(button) && isCommentReplyTrigger(triggerLabel(button)));
    let clicked = 0;
    for (const button of candidates.slice(0, maxClicks)) {
      button.scrollIntoView?.({ block: "center", inline: "nearest" });
      await sleep(100);
      safeClick(button);
      clicked += 1;
      await sleep(350);
      if (clicked >= maxClicks || stopped) break;
    }
    return clicked;
  }

  function isCommentReplyTrigger(label) {
    const value = String(label || "").toLowerCase();
    if (!value || isHiddenEmailTrigger(value)) return false;
    if (value === "reply" || value === "\u56de\u590d") return false;
    return /(?:view|show)\s*(?:all\s*)?\d*\s*repl(?:y|ies)/i.test(value)
      || /(?:view|show)\s*repl(?:y|ies)/i.test(value)
      || /(?:\u67e5\u770b|\u5c55\u5f00|\u663e\u793a).{0,16}\u56de\u590d/.test(value)
      || /\d+\s*(?:\u6761|\u5247)?\s*\u56de\u590d/.test(value);
  }

  function scrollCommentArea() {
    const target = findScrollable([
      "ytd-comments#comments",
      "ytd-engagement-panel-section-list-renderer[target-id='engagement-panel-comments-section'] #contents",
      "ytd-engagement-panel-section-list-renderer #contents",
      "#comments",
      "#sections"
    ]);
    if (target) {
      target.scrollTop += 1000;
      return;
    }
    window.scrollBy({ top: 1100, left: 0, behavior: "smooth" });
  }

  function findScrollable(selectors) {
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (node && node.scrollHeight > node.clientHeight + 80) return node;
    }
    return null;
  }

  function normalizeSettings(settings) {
    return {
      maxVideos: clampNumber(settings.maxVideos, 1, 100, 5),
      maxComments: clampNumber(settings.maxComments ?? settings.maxCommentsPerVideo, 0, 200, 50),
      maxCommenterProfiles: clampNumber(settings.maxCommenterProfiles ?? settings.maxCommenterProfilesPerVideo, 0, 200, 50),
      scrollRounds: clampNumber(settings.scrollRounds, 0, 30, 8),
      searchScrollRounds: clampNumber(settings.searchScrollRounds, 0, 30, 10),
      waitMs: clampNumber(settings.waitMs, 250, 3000, 900)
    };
  }

  function detectPageKind() {
    if (/\/results\b/i.test(location.pathname)) return "search";
    if (/\/watch\b|\/shorts\//i.test(location.pathname)) return "video";
    if (utils().normalizeChannelUrl(location.href)) return "channel";
    return "other";
  }

  function inferKeywordFromUrl() {
    try {
      return new URL(location.href).searchParams.get("search_query") || "";
    } catch {
      return "";
    }
  }

  function detector() {
    return globalThis.X9YoutubeContact || { detectContacts: () => [] };
  }

  function utils() {
    return globalThis.X9YoutubeUtils || {};
  }

  function first(selectors) {
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (node) return node;
    }
    return null;
  }

  function firstWithin(root, selectors) {
    if (!root) return null;
    for (const selector of selectors) {
      const node = root.querySelector(selector);
      if (node) return node;
    }
    return null;
  }

  function firstAnchor(selectors) {
    return first(selectors);
  }

  function text(node) {
    return String(node?.innerText || node?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function visibleText() {
    return text(document.body);
  }

  function longestText(values) {
    return values
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length)[0] || "";
  }

  function readPath(root, path) {
    let current = root;
    for (const key of path) {
      if (!current || typeof current !== "object") return "";
      current = current[key];
    }
    return current || "";
  }

  function extractBalancedJson(textValue, startIndex) {
    let depth = 0;
    let inString = false;
    let escape = false;
    for (let index = startIndex; index < textValue.length; index += 1) {
      const char = textValue[index];
      if (inString) {
        if (escape) {
          escape = false;
        } else if (char === "\\") {
          escape = true;
        } else if (char === "\"") {
          inString = false;
        }
        continue;
      }
      if (char === "\"") {
        inString = true;
      } else if (char === "{") {
        depth += 1;
      } else if (char === "}") {
        depth -= 1;
        if (depth === 0) return textValue.slice(startIndex, index + 1);
      }
    }
    return "";
  }

  function cleanDetailText(value) {
    let cleaned = String(value || "").replace(/\s+/g, " ").trim();
    for (const marker of [
      "var ytInitialPlayerResponse",
      "ytInitialPlayerResponse =",
      "\"streamingData\"",
      "signatureCipher"
    ]) {
      const index = cleaned.indexOf(marker);
      if (index > 0) cleaned = cleaned.slice(0, index).trim();
    }
    return cleaned;
  }

  function meta(name) {
    return document.querySelector(`meta[name="${name}"], meta[property="og:${name}"]`)?.content || "";
  }

  function absoluteUrl(href) {
    if (!href) return "";
    try {
      return new URL(href, location.origin).toString();
    } catch {
      return "";
    }
  }

  function setInputValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (setter && input instanceof HTMLInputElement) setter.call(input, value);
    else input.value = value;
  }

  function safeClick(node) {
    try {
      node.click();
    } catch {
      node.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    }
  }

  function isVisible(node) {
    const rect = node?.getBoundingClientRect?.();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(node);
    return style.visibility !== "hidden" && style.display !== "none";
  }

  function unique(items) {
    return Array.from(new Set((items || []).filter(Boolean)));
  }

  function truncate(value, max) {
    const textValue = String(value || "");
    return textValue.length > max ? textValue.slice(0, max) : textValue;
  }

  function clampNumber(value, min, max, fallback) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(min, Math.min(max, Math.round(parsed)));
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function errorText(error) {
    return error instanceof Error ? error.message : String(error);
  }
})();
