(() => {
if (globalThis.__TCLAB_CONTENT_SCRIPT_LOADED__) {
  return;
}
globalThis.__TCLAB_CONTENT_SCRIPT_LOADED__ = true;

const TCLAB_EMAIL_REGEX = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const TCLAB_EMAIL_VALIDATION_REGEX = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const TCLAB_FAKE_EMAILS = new Set([
  'example@example.com',
  'test@test.com',
  'yourname@email.com',
  'name@example.com'
]);

const TCLAB_USEFUL_EXTERNAL_DOMAINS = [
  'linktr.ee',
  'beacons.ai',
  'instagram.com',
  'youtube.com',
  'youtu.be',
  'bio.site',
  'msha.ke',
  'solo.to',
  'stan.store'
];

const TCLAB_BLOCKED_EXTERNAL_DOMAINS = new Set([
  'tiktok.com',
  'www.tiktok.com',
  'm.tiktok.com',
  'vm.tiktok.com'
]);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message) {
    return false;
  }

  try {
    if (message.type === 'TCLAB_COLLECT_PAGE') {
      sendResponse({
        ok: true,
        data: tclabCollectPage()
      });
      return true;
    }

    if (message.type === 'TCLAB_SCROLL_PAGE') {
      sendResponse({
        ok: true,
        data: tclabScrollPage()
      });
      return true;
    }

    if (message.type === 'TCLAB_SCROLL_SEARCH_RESULTS') {
      tclabScrollSearchResults(message.options || {})
        .then((data) => {
          sendResponse({
            ok: true,
            data
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : String(error)
          });
        });
      return true;
    }

    if (message.type === 'TCLAB_SEARCH_TIKTOK') {
      tclabSearchTikTok(message.keyword || '')
        .then((data) => {
          sendResponse({
            ok: true,
            data
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : String(error)
          });
        });
      return true;
    }

    if (message.type === 'TCLAB_CLICK_VIDEO_TAB') {
      tclabClickVideoTab()
        .then((data) => {
          sendResponse({
            ok: true,
            data
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : String(error)
          });
        });
      return true;
    }

    if (message.type === 'TCLAB_CLOSE_VIDEO_VIEW') {
      tclabCloseVideoView()
        .then((data) => {
          sendResponse({
            ok: true,
            data
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : String(error)
          });
        });
      return true;
    }

    if (message.type === 'TCLAB_WAIT_SEARCH_RESULTS') {
      tclabWaitForSearchResults(message.timeoutMs || 4_000)
        .then((data) => {
          sendResponse({
            ok: true,
            data
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : String(error)
          });
        });
      return true;
    }

    return false;
  } catch (error) {
    sendResponse({
      ok: false,
      error: error instanceof Error ? error.message : String(error)
    });
    return true;
  }
});

function tclabCollectPage() {
  const visibleText = document.body?.innerText || '';
  const currentUrl = window.location.href;
  const username = tclabExtractUsername(currentUrl);
  const videos = tclabCollectVisibleVideos();
  const currentVideo = tclabCollectCurrentVideo(currentUrl, visibleText);
  const emails = tclabExtractEmails(visibleText);
  const externalLinks = tclabCollectExternalLinks();
  const profile = username
    ? tclabCollectProfile(currentUrl, username, visibleText, emails, externalLinks)
    : null;

  const isSearchVideoPage = tclabIsSearchResultsPage();
  const noMoreResults = tclabHasNoMoreSearchResults();

  return {
    url: currentUrl,
    title: document.title || '',
    visibleText,
    gate: tclabDetectAccessGate(visibleText),
    inferredSearchKeyword: tclabInferSearchKeyword(currentUrl),
    isTikTok: location.hostname.endsWith('tiktok.com'),
    isSearchVideoPage,
    isProfilePage: Boolean(profile) && !/\/video\/\d+/i.test(currentUrl),
    isVideoPage: !isSearchVideoPage && (/\/@[^/]+\/video\/\d+/i.test(currentUrl) || Boolean(currentVideo)),
    noMoreResults,
    videos,
    currentVideo,
    profile
  };
}

function tclabIsSearchResultsPage() {
  const hasSearchCards = Boolean(document.querySelector('[data-e2e="search_video-item"], [id^="grid-item-container-"], [data-e2e="search-card-desc"]'));
  const hasBrowseClose = Boolean(tclabFindVideoCloseButton());
  return hasSearchCards && (/\/search(?:\/video)?\b/i.test(location.pathname) || !hasBrowseClose);
}

function tclabScrollPage() {
  const distance = 900 + Math.round(Math.random() * 700);
  window.scrollBy({
    top: distance,
    left: 0,
    behavior: 'smooth'
  });

  return {
    scrollY: window.scrollY,
    distance
  };
}

async function tclabScrollSearchResults(options = {}) {
  if (tclabFindVideoCloseButton()) {
    throw new Error('当前仍在视频播放页面，请先点击指定关闭按钮后再加载搜索结果。');
  }

  const timeoutMs = tclabClampNumber(options.timeoutMs, 1_000, 20_000, 6_000);
  const maxSteps = tclabClampNumber(options.maxSteps, 1, 10, 5);
  const startedAt = Date.now();
  const beforeVideos = tclabCollectVisibleVideos();
  const beforeKeys = new Set(beforeVideos.map((video) => tclabGetVideoIdentityKey(video.video_url) || tclabCanonicalUrl(video.video_url)).filter(Boolean));
  const beforeCount = beforeKeys.size;
  const beforeScrollY = window.scrollY;
  const beforeScrollHeight = tclabGetScrollHeight();
  const scrollTarget = tclabFindSearchScrollTarget();
  let steps = 0;
  let lastDistance = 0;

  if (tclabHasNoMoreSearchResults()) {
    return {
      loaded: false,
      noMoreResults: true,
      steps,
      distance: lastDistance,
      beforeCount,
      afterCount: beforeCount,
      newCount: 0,
      beforeScrollY,
      afterScrollY: window.scrollY,
      scrollHeight: tclabGetScrollHeight()
    };
  }

  while (steps < maxSteps && Date.now() - startedAt < timeoutMs) {
    steps += 1;
    lastDistance = Math.max(760, Math.round(window.innerHeight * (0.85 + Math.random() * 0.45)));
    tclabScrollTargetBy(scrollTarget, lastDistance);
    await tclabSleep(260 + Math.round(Math.random() * 260));

    const afterVideos = tclabCollectVisibleVideos();
    const afterKeys = new Set(afterVideos.map((video) => tclabGetVideoIdentityKey(video.video_url) || tclabCanonicalUrl(video.video_url)).filter(Boolean));
    const newKeys = Array.from(afterKeys).filter((key) => !beforeKeys.has(key));
    const scrollHeightGrew = tclabGetScrollHeight() > beforeScrollHeight + 80;

    if (newKeys.length > 0 || afterKeys.size > beforeCount || scrollHeightGrew) {
      await tclabSleep(350);
      const settledVideos = tclabCollectVisibleVideos();
      const settledKeys = new Set(settledVideos.map((video) => tclabGetVideoIdentityKey(video.video_url) || tclabCanonicalUrl(video.video_url)).filter(Boolean));
      return {
        loaded: true,
        steps,
        distance: lastDistance,
        beforeCount,
        afterCount: settledKeys.size,
        newCount: Array.from(settledKeys).filter((key) => !beforeKeys.has(key)).length,
        beforeScrollY,
        afterScrollY: window.scrollY,
        scrollHeight: tclabGetScrollHeight(),
        noMoreResults: tclabHasNoMoreSearchResults()
      };
    }

    if (tclabHasNoMoreSearchResults()) {
      break;
    }
  }

  const finalVideos = tclabCollectVisibleVideos();
  const finalKeys = new Set(finalVideos.map((video) => tclabGetVideoIdentityKey(video.video_url) || tclabCanonicalUrl(video.video_url)).filter(Boolean));
  return {
    loaded: false,
    noMoreResults: tclabHasNoMoreSearchResults(),
    steps,
    distance: lastDistance,
    beforeCount,
    afterCount: finalKeys.size,
    newCount: Array.from(finalKeys).filter((key) => !beforeKeys.has(key)).length,
    beforeScrollY,
    afterScrollY: window.scrollY,
    scrollHeight: tclabGetScrollHeight()
  };
}

function tclabHasNoMoreSearchResults() {
  const direct = Array.from(document.querySelectorAll('[class*="NoMoreResults"], [class*="DivNoMoreResults"], div, span'))
    .some((element) => {
      if (!tclabIsVisible(element)) {
        return false;
      }
      const text = tclabNormalizeWhitespace(element.innerText || element.textContent || '');
      return text === '暂时没有更多了' || /^no more results$/i.test(text) || /^no more$/i.test(text);
    });

  if (direct) {
    return true;
  }

  return tclabNormalizeWhitespace(document.body?.innerText || '').includes('暂时没有更多了');
}

function tclabFindSearchScrollTarget() {
  const candidates = [
    document.scrollingElement,
    document.documentElement,
    document.body,
    ...Array.from(document.querySelectorAll('main, [data-e2e*="search" i], [class*="DivSearch"], [class*="DivMain"], [class*="Container"]'))
  ].filter(Boolean);

  return candidates.find((element) => {
    return element.scrollHeight > element.clientHeight + 120
      && tclabIsVisible(element);
  }) || document.scrollingElement || document.documentElement || document.body;
}

function tclabScrollTargetBy(target, distance) {
  const wheelEvent = new WheelEvent('wheel', {
    bubbles: true,
    cancelable: true,
    deltaY: distance,
    deltaMode: 0,
    view: window
  });

  target?.dispatchEvent(wheelEvent);
  document.dispatchEvent(new WheelEvent('wheel', {
    bubbles: true,
    cancelable: true,
    deltaY: distance,
    deltaMode: 0,
    view: window
  }));

  if (target === document.scrollingElement || target === document.documentElement || target === document.body) {
    window.scrollBy({
      top: distance,
      left: 0,
      behavior: 'smooth'
    });
    return;
  }

  target.scrollBy({
    top: distance,
    left: 0,
    behavior: 'smooth'
  });
}

function tclabGetScrollHeight() {
  return Math.max(
    document.scrollingElement?.scrollHeight || 0,
    document.documentElement?.scrollHeight || 0,
    document.body?.scrollHeight || 0
  );
}

async function tclabSearchTikTok(keyword) {
  const searchKeyword = tclabNormalizeWhitespace(keyword);
  if (!searchKeyword) {
    throw new Error('请输入关键词。');
  }

  let revealedSearch = false;
  let input = tclabFindSearchInput();
  if (!input) {
    const trigger = tclabFindSearchTrigger();
    if (trigger) {
      trigger.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      tclabClickElement(trigger);
      revealedSearch = true;
      input = await tclabWaitForSearchInput(4_000);
    }
  }

  if (!input && tclabNavSearchboxMatchesKeyword(searchKeyword)) {
    return {
      method: 'nav_searchbox_already_matches',
      keyword: searchKeyword
    };
  }

  if (!input) {
    const navSearch = tclabFindNavSearchbox();
    if (navSearch) {
      tclabClickElement(navSearch);
      revealedSearch = true;
      input = await tclabWaitForSearchInput(4_000);
    }
  }

  if (!input) {
    throw new Error('TikTok 搜索框仍未展开。请先手动点击顶部搜索框一次，保持搜索面板打开后重试。');
  }

  input.focus();
  tclabSetInputValue(input, searchKeyword);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));

  const form = input.closest('form');
  const searchButton = form?.querySelector('button[type="submit"], button[aria-label*="Search" i], button[data-e2e*="search" i]')
    || document.querySelector('[data-e2e="search-button"], button[aria-label*="Search" i]');

  if (searchButton && tclabIsVisible(searchButton)) {
    tclabClickElement(searchButton);
    return {
      method: revealedSearch ? 'revealed_input_button' : 'input_button',
      keyword: searchKeyword
    };
  }

  input.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter',
    code: 'Enter',
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true
  }));
  input.dispatchEvent(new KeyboardEvent('keyup', {
    key: 'Enter',
    code: 'Enter',
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true
  }));

  if (form && typeof form.requestSubmit === 'function') {
    setTimeout(() => form.requestSubmit(), 150);
  }

  return {
    method: revealedSearch ? 'revealed_input_enter' : 'input_enter',
    keyword: searchKeyword
  };
}

async function tclabClickVideoTab() {
  if (/\/search\/video\b/i.test(location.pathname)) {
    const ready = await tclabWaitForVideoSearchResults(6_000);
    return {
      method: 'already_on_video_tab',
      ready: ready.ready,
      cardCount: ready.cardCount
    };
  }

  const tab = tclabFindVideoSearchTab();
  if (!tab) {
    throw new Error('没有看到“视频”选项卡。请先确认搜索结果页顶部有“综合 / 用户 / 视频 / 直播 / 照片”这一排。');
  }

  const text = tclabNormalizeWhitespace(tab.innerText || tab.textContent || tab.getAttribute('aria-label') || '');
  tab.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
  await tclabSleep(160);
  tclabClickElementAtPoint(tab, 0.5, 0.5);
  await tclabSleep(320);

  if (!/\/search\/video\b/i.test(location.pathname)) {
    tclabClickElement(tab);
  }

  const ready = await tclabWaitForVideoSearchResults(7_000);
  if (!ready.ready) {
    throw new Error('已点击“视频”选项卡，但还没有检测到视频搜索结果卡片。请稍等页面加载完成后再开始。');
  }

  return {
    method: 'click_visible_video_tab',
    text,
    ready: ready.ready,
    cardCount: ready.cardCount
  };
}

async function tclabWaitForVideoSearchResults(timeoutMs = 6_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const cardCount = tclabCountSearchResultCards();
    const pathReady = /\/search\/video\b/i.test(location.pathname);
    const tabReady = cardCount > 0 && tclabIsVideoTabVisuallyActive();
    if (pathReady || tabReady) {
      return {
        ready: true,
        cardCount,
        path: location.pathname
      };
    }

    await tclabSleep(180);
  }

  return {
    ready: false,
    cardCount: tclabCountSearchResultCards(),
    path: location.pathname
  };
}

function tclabIsVideoTabVisuallyActive() {
  const tab = tclabFindVideoSearchTab();
  if (!tab) {
    return false;
  }

  const container = tab.closest('[data-testid="tux-web-tab-bar-container"], [class*="tux-button"]') || tab;
  const styleText = `${container.getAttribute('style') || ''} ${tab.getAttribute('style') || ''}`;
  if (/ui-text-1/i.test(styleText)) {
    return true;
  }

  const indicator = document.querySelector('[class*="tux-tabbar__indicator"]');
  if (!indicator || !tclabIsVisible(indicator)) {
    return false;
  }

  const tabRect = tab.getBoundingClientRect();
  const indicatorRect = indicator.getBoundingClientRect();
  const tabCenter = tabRect.left + tabRect.width / 2;
  return tabCenter >= indicatorRect.left && tabCenter <= indicatorRect.right;
}

async function tclabCloseVideoView() {
  const closeButton = tclabFindVideoCloseButton();
  if (!closeButton) {
    throw new Error('没有找到指定的视频关闭按钮 button[data-e2e="browse-close"][aria-label="关闭"]。');
  }

  tclabClickCloseButton(closeButton);
  return {
    method: 'click_browse_close_once',
    target: tclabDescribeElement(closeButton)
  };
}

function tclabFindVideoCloseButton() {
  const button = document.querySelector('button[data-e2e="browse-close"][aria-label="\u5173\u95ed"]');
  return button && tclabIsVisible(button) ? button : null;
}

function tclabClickCloseButton(button) {
  button.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
  tclabClickElement(button);
}

async function tclabWaitForSearchResults(timeoutMs = 4_000) {
  const startedAt = Date.now();
  let count = 0;

  while (Date.now() - startedAt < timeoutMs) {
    count = tclabCountSearchResultCards();
    if (count > 0 && !tclabFindVideoCloseButton()) {
      return {
        found: true,
        count
      };
    }

    await tclabSleep(120);
  }

  return {
    found: false,
    count: tclabCountSearchResultCards()
  };
}

function tclabCountSearchResultCards() {
  return document.querySelectorAll('[data-e2e="search_video-item"], [id^="grid-item-container-"], [data-e2e="search-card-desc"]').length;
}

function tclabFindSearchInput() {
  const selectors = [
    'input[data-e2e="search-user-input"]',
    '[data-e2e="search-user-input"] input',
    '[data-e2e*="search" i] input',
    '[data-e2e*="search" i] textarea',
    'form input[type="search"]',
    'form input[placeholder*="Search" i]',
    'form input[placeholder*="search" i]',
    'form input[type="text"]',
    'input[placeholder*="Search" i]',
    'input[placeholder*="search" i]',
    'input[type="search"]',
    'input[name="q"]',
    'textarea[placeholder*="Search" i]',
    '[role="combobox"]',
    '[contenteditable="true"][data-e2e*="search" i]',
    '[contenteditable="true"][aria-label*="Search" i]'
  ];

  for (const selector of selectors) {
    const input = document.querySelector(selector);
    if (input && tclabIsVisible(input) && tclabLooksLikeSearchInput(input)) {
      return input;
    }
  }

  return Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"], [role="combobox"]'))
    .find((input) => tclabIsVisible(input) && tclabLooksLikeSearchInput(input))
    || null;
}

function tclabLooksLikeSearchInput(element) {
  if (!element || element.disabled || element.readOnly) {
    return false;
  }

  const descriptor = [
    element.getAttribute('data-e2e') || '',
    element.getAttribute('aria-label') || '',
    element.getAttribute('placeholder') || '',
    element.getAttribute('name') || '',
    element.getAttribute('id') || '',
    element.getAttribute('role') || '',
    element.closest('form')?.innerText || ''
  ].join(' ');

  return /search|\u641c\u7d22/i.test(descriptor);
}

function tclabFindSearchTrigger() {
  const selectors = [
    '[data-e2e="nav-search"]',
    'button[data-e2e="nav-search"]',
    'button[role="searchbox"]',
    '[data-e2e="search-button"]',
    '[data-e2e*="search" i] button',
    'button[data-e2e*="search" i]',
    'button[aria-label*="Search" i]',
    'a[aria-label*="Search" i]',
    '[role="button"][aria-label*="Search" i]',
    '[role="button"][data-e2e*="search" i]'
  ];

  for (const selector of selectors) {
    const trigger = document.querySelector(selector);
    if (trigger && tclabIsVisible(trigger)) {
      return tclabClosestClickable(trigger);
    }
  }

  return Array.from(document.querySelectorAll('a, button, [role="button"], [tabindex]'))
    .map((element) => tclabClosestClickable(element))
    .find((element) => {
      if (!element || !tclabIsVisible(element)) {
        return false;
      }

      const descriptor = [
        element.getAttribute('data-e2e') || '',
        element.getAttribute('aria-label') || '',
        element.getAttribute('title') || '',
        element.innerText || element.textContent || ''
      ].join(' ');

      return /search|\u641c\u7d22/i.test(descriptor);
    })
    || null;
}

function tclabFindNavSearchbox() {
  return Array.from(document.querySelectorAll('[data-e2e="nav-search"], button[role="searchbox"], [role="searchbox"]'))
    .find((element) => tclabIsVisible(element) && /search|\u641c\u7d22/i.test([
      element.getAttribute('data-e2e') || '',
      element.getAttribute('aria-label') || '',
      element.getAttribute('role') || ''
    ].join(' ')))
    || null;
}

function tclabNavSearchboxMatchesKeyword(keyword) {
  const navSearch = tclabFindNavSearchbox();
  if (!navSearch) {
    return false;
  }

  const text = tclabNormalizeWhitespace(navSearch.innerText || navSearch.textContent || '');
  return tclabNormalizeSearchText(text).includes(tclabNormalizeSearchText(keyword));
}

function tclabFindVideoSearchTab() {
  const tuxVideoTab = tclabFindTuxVideoTab();
  if (tuxVideoTab) {
    return tuxVideoTab;
  }

  const searchVideoLink = Array.from(document.querySelectorAll('a[href]'))
    .find((anchor) => {
      if (!tclabIsVisible(anchor)) {
        return false;
      }

      try {
        const url = new URL(anchor.href, location.href);
        return /\/search\/video\b/i.test(url.pathname);
      } catch {
        return false;
      }
    });

  if (searchVideoLink) {
    return searchVideoLink;
  }

  const labels = new Set(['video', 'videos', '\u89c6\u9891', '\u5f71\u7247']);
  const candidates = Array.from(document.querySelectorAll('a, button, [role="tab"], [role="button"], span, div'));

  for (const element of candidates) {
    if (!tclabIsVisible(element)) {
      continue;
    }

    const text = tclabNormalizeWhitespace([
      element.getAttribute('aria-label') || '',
      element.getAttribute('title') || '',
      element.innerText || element.textContent || ''
    ].join(' ')).toLowerCase();

    if (!labels.has(text)) {
      continue;
    }

    const clickable = tclabClosestClickable(element);
    if (clickable && tclabIsVisible(clickable)) {
      return clickable;
    }
  }

  return null;
}

function tclabFindTuxVideoTab() {
  const candidates = Array.from(document.querySelectorAll([
    'button[data-testid="tux-web-tab-bar"]',
    '[data-testid="tux-web-tab-bar-container"] button',
    '[data-testid="tux-web-tab-bar"]'
  ].join(',')));

  return candidates.find((element) => {
    if (!tclabIsVisible(element)) {
      return false;
    }

    const text = tclabNormalizeWhitespace(element.innerText || element.textContent || '');
    return /^(\u89c6\u9891|video|videos)$/i.test(text);
  }) || null;
}

function tclabClosestClickable(element) {
  return element.closest('a, button, [role="tab"], [role="button"]') || element;
}

async function tclabWaitForSearchInput(timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const input = tclabFindSearchInput();
    if (input) {
      return input;
    }
    await tclabSleep(250);
  }
  return null;
}

function tclabClickElement(element) {
  const rect = element.getBoundingClientRect();
  const clientX = Math.round(rect.left + rect.width / 2);
  const clientY = Math.round(rect.top + rect.height / 2);
  tclabClickAt(element, clientX, clientY);
}

function tclabClickElementAtPoint(element, xRatio = 0.5, yRatio = 0.5) {
  const rect = element.getBoundingClientRect();
  const clientX = Math.round(rect.left + rect.width * xRatio);
  const clientY = Math.round(rect.top + rect.height * yRatio);
  const topElement = document.elementFromPoint(clientX, clientY);
  tclabClickAt(topElement || element, clientX, clientY);
}

function tclabClickAt(element, clientX, clientY) {
  const eventBase = {
    bubbles: true,
    cancelable: true,
    composed: true,
    view: window,
    clientX,
    clientY,
    screenX: window.screenX + clientX,
    screenY: window.screenY + clientY
  };

  if (typeof PointerEvent !== 'undefined') {
    element.dispatchEvent(new PointerEvent('pointerover', { ...eventBase, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
    element.dispatchEvent(new PointerEvent('pointerenter', { ...eventBase, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
    element.dispatchEvent(new PointerEvent('pointerdown', { ...eventBase, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 1 }));
    element.dispatchEvent(new PointerEvent('pointerup', { ...eventBase, pointerId: 1, pointerType: 'mouse', isPrimary: true, buttons: 0 }));
  }

  element.dispatchEvent(new MouseEvent('mouseover', eventBase));
  element.dispatchEvent(new MouseEvent('mouseenter', eventBase));
  element.dispatchEvent(new MouseEvent('mousedown', { ...eventBase, button: 0, buttons: 1 }));
  element.dispatchEvent(new MouseEvent('mouseup', { ...eventBase, button: 0, buttons: 0 }));
  element.dispatchEvent(new MouseEvent('click', { ...eventBase, button: 0, buttons: 0 }));

  if (typeof element.click === 'function') {
    element.click();
  }
}

function tclabDescribeElement(element) {
  if (!element) {
    return 'none';
  }

  const tag = element.tagName ? element.tagName.toLowerCase() : 'node';
  const dataE2e = element.getAttribute?.('data-e2e');
  const role = element.getAttribute?.('role');
  const id = element.getAttribute?.('id');
  return [tag, dataE2e ? `[data-e2e=${dataE2e}]` : '', role ? `[role=${role}]` : '', id ? `#${id}` : '']
    .filter(Boolean)
    .join('');
}

function tclabSetInputValue(input, value) {
  if (input.isContentEditable) {
    input.textContent = value;
    return;
  }

  if (!(input instanceof HTMLInputElement) && !(input instanceof HTMLTextAreaElement)) {
    input.textContent = value;
    input.setAttribute('value', value);
    return;
  }

  const prototype = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (setter) {
    setter.call(input, value);
  } else {
    input.value = value;
  }
}

function tclabDetectAccessGate(text) {
  const body = String(text || '').toLowerCase();
  const captchaSignals = [
    'captcha',
    'verification',
    'verify',
    'unusual activity',
    'something went wrong',
    'too many attempts',
    'not available in your region',
    'age-restricted',
    'age restricted'
  ];
  const loginSignals = [
    'log in to tiktok',
    'log in or sign up',
    'sign up for tiktok',
    'continue with google',
    'continue with facebook',
    'continue with apple'
  ];

  const captcha = captchaSignals.find((signal) => body.includes(signal));
  if (captcha) {
    return { type: 'verification', matchedText: captcha };
  }

  const login = loginSignals.find((signal) => body.includes(signal));
  if (location.pathname.toLowerCase().includes('/login') || login) {
    return { type: 'login', matchedText: login || '/login' };
  }

  const shortLoginWall = body.includes('log in') && body.includes('sign up') && body.length < 2500;
  if (shortLoginWall) {
    return { type: 'login', matchedText: 'log in / sign up' };
  }

  return { type: 'none', matchedText: '' };
}

function tclabCollectVisibleVideos() {
  const seen = new Set();
  const videos = [];
  const links = Array.from(document.querySelectorAll('a[href*="/video/"]'));

  for (const link of links) {
    if (!tclabIsVisible(link)) {
      continue;
    }

    const href = tclabCanonicalUrl(link.href);
    const username = tclabExtractUsername(href);
    if (!href || !username || seen.has(href)) {
      continue;
    }

    seen.add(href);
    const container = tclabFindSearchVideoCard(link) || link.closest('article, div[data-e2e], div');
    const caption = container?.querySelector?.('[data-e2e="search-card-video-caption"], [data-e2e="search-card-desc"]')?.innerText || '';
    const uniqueId = container?.querySelector?.('[data-e2e="search-card-user-unique-id"]')?.innerText || '';
    const userLink = container?.querySelector?.('[data-e2e="search-card-user-link"], a[href^="/@"]');
    const altText = container?.querySelector?.('img[alt]')?.getAttribute('alt') || '';
    const text = tclabNormalizeWhitespace([
      link.getAttribute('title') || '',
      link.getAttribute('aria-label') || '',
      caption,
      altText,
      container?.innerText || link.innerText || link.textContent || ''
    ].join(' '));
    const cardUsername = tclabNormalizeWhitespace(uniqueId || tclabExtractUsername(userLink?.href || '')) || username;

    videos.push({
      creator_username: cardUsername,
      creator_profile_url: `https://www.tiktok.com/@${encodeURIComponent(cardUsername)}`,
      video_url: href,
      video_title: tclabTruncate(text || href, 500),
      video_description: tclabTruncate(text, 1000)
    });
  }

  return videos;
}

function tclabFindSearchVideoCard(link) {
  let node = link;
  for (let depth = 0; node && depth < 8; depth += 1) {
    if (node.matches?.('[id^="grid-item-container-"], [class*="DivItemContainer"], article')) {
      return node;
    }
    node = node.parentElement;
  }

  return link.closest('[data-e2e="search_video-item"], article') || null;
}

function tclabCollectCurrentVideo(currentUrl, visibleText) {
  const mainVideo = tclabFindMainVisibleVideo();
  const container = mainVideo ? tclabFindVideoContainer(mainVideo) : null;
  const playbackState = tclabGetVideoPlaybackState(mainVideo, visibleText);
  const profileLink = tclabFindProfileLinkInContainer(container) || tclabFindVisibleCreatorProfileLink();
  const linkUsername = profileLink ? tclabExtractUsername(profileLink.href) : '';
  const urlUsername = tclabExtractUsername(currentUrl);
  const username = linkUsername || urlUsername;
  if (!username) {
    return null;
  }

  const containerText = tclabNormalizeWhitespace(container?.innerText || '');
  const text = containerText || tclabTruncate(visibleText, 1200);
  const canonicalCurrentUrl = tclabCanonicalUrl(currentUrl);
  const urlMatchesVisibleCreator = !urlUsername || urlUsername === username;
  const videoUrl = urlMatchesVisibleCreator
    ? canonicalCurrentUrl
    : `${canonicalCurrentUrl}#visible-${encodeURIComponent(username)}-${tclabHashText(text).slice(0, 10)}`;

  return {
    creator_username: username,
    creator_profile_url: `https://www.tiktok.com/@${encodeURIComponent(username)}`,
    video_url: videoUrl,
    video_title: tclabTruncate(document.title || text || videoUrl, 500),
    video_description: tclabTruncate(text || visibleText, 1000),
    playback_state: playbackState,
    video_fingerprint: `${username}|${tclabHashText(videoUrl)}|${tclabHashText(text).slice(0, 12)}`
  };
}

function tclabGetVideoPlaybackState(video, visibleText) {
  const bodyText = String(visibleText || '').toLowerCase();
  const unavailableSignals = [
    'video currently unavailable',
    'video unavailable',
    'couldn\'t play video',
    'cannot play video',
    'this video is unavailable',
    'this video is not available',
    'not available in your region',
    'something went wrong',
    '视频不可用',
    '无法播放',
    '暂时无法观看'
  ];
  const matchedSignal = unavailableSignals.find((signal) => bodyText.includes(signal.toLowerCase()));

  if (!video) {
    return {
      playable: false,
      reason: matchedSignal || 'no_visible_video'
    };
  }

  if (matchedSignal) {
    return {
      playable: false,
      reason: matchedSignal
    };
  }

  if (video.error) {
    return {
      playable: false,
      reason: `media_error_${video.error.code || 'unknown'}`
    };
  }

  const hasSource = Boolean(video.currentSrc || video.src || video.querySelector('source[src]'));
  const durationKnown = Number.isFinite(video.duration) && video.duration > 0;
  const hasBufferedData = Boolean(video.buffered && video.buffered.length > 0);
  const noSourceNetworkState = typeof HTMLMediaElement !== 'undefined'
    && video.networkState === HTMLMediaElement.NETWORK_NO_SOURCE;

  if (noSourceNetworkState) {
    return {
      playable: false,
      reason: 'network_no_source'
    };
  }

  if (!hasSource && video.readyState === 0 && !durationKnown && !hasBufferedData) {
    return {
      playable: false,
      reason: 'no_video_source'
    };
  }

  return {
    playable: true,
    reason: video.paused ? 'visible_video_paused_or_ready' : 'visible_video_playing',
    readyState: video.readyState,
    networkState: video.networkState,
    currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
    duration: durationKnown ? video.duration : null
  };
}

function tclabFindMainVisibleVideo() {
  const videos = Array.from(document.querySelectorAll('video')).filter((video) => tclabIsVisible(video));
  let best = null;
  let bestScore = 0;

  for (const video of videos) {
    const rect = video.getBoundingClientRect();
    const visibleWidth = Math.max(0, Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0));
    const visibleHeight = Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));
    const area = visibleWidth * visibleHeight;
    if (area > bestScore) {
      best = video;
      bestScore = area;
    }
  }

  return best;
}

function tclabFindVideoContainer(video) {
  let node = video;
  for (let depth = 0; node && depth < 8; depth += 1) {
    const links = Array.from(node.querySelectorAll?.('a[href*="/@"]') || []);
    if (links.some((link) => tclabIsVisible(link) && tclabExtractUsername(link.href) && !link.href.includes('/video/'))) {
      return node;
    }
    node = node.parentElement;
  }
  return video?.parentElement || null;
}

function tclabFindProfileLinkInContainer(container) {
  if (!container) {
    return null;
  }

  return Array.from(container.querySelectorAll('a[href*="/@"]'))
    .find((link) => tclabIsVisible(link) && tclabExtractUsername(link.href) && !link.href.includes('/video/'))
    || null;
}

function tclabFindVisibleCreatorProfileLink() {
  return Array.from(document.querySelectorAll('a[href*="/@"]'))
    .find((link) => {
      if (!tclabIsVisible(link) || link.href.includes('/video/') || !tclabExtractUsername(link.href)) {
        return false;
      }

      const rect = link.getBoundingClientRect();
      return rect.top >= 0
        && rect.top <= window.innerHeight
        && rect.left >= window.innerWidth * 0.18;
    })
    || null;
}

function tclabCollectProfile(currentUrl, username, visibleText, emails, externalLinks) {
  const usernameText = tclabTextFromSelectors(['[data-e2e="user-title"]', 'h1']);
  const nickname = tclabTextFromSelectors(['[data-e2e="user-subtitle"]', 'h2']);
  const bio = tclabTextFromSelectors(['[data-e2e="user-bio"]']) || tclabGuessBio(visibleText);
  const followersRaw = tclabTextFromSelectors(['[data-e2e="followers-count"]']) || tclabExtractMetric(visibleText, ['Followers', 'Follower']);
  const followingRaw = tclabTextFromSelectors(['[data-e2e="following-count"]']) || tclabExtractMetric(visibleText, ['Following']);
  const likesRaw = tclabTextFromSelectors(['[data-e2e="likes-count"]']) || tclabExtractMetric(visibleText, ['Likes']);
  const normalizedUsername = (usernameText || username).replace(/^@/, '').trim();

  return {
    username: normalizedUsername,
    nickname: tclabTruncate(nickname, 300),
    profile_url: `https://www.tiktok.com/@${encodeURIComponent(normalizedUsername)}`,
    bio: tclabTruncate(bio, 2000),
    followers_raw: followersRaw,
    followers_count: tclabParseCompactNumber(followersRaw),
    following_raw: followingRaw,
    likes_raw: likesRaw,
    email: emails[0] || '',
    emails,
    external_links: externalLinks,
    visible_text: visibleText,
    source_url: currentUrl
  };
}

function tclabExtractEmails(text) {
  const matches = text.match(TCLAB_EMAIL_REGEX) || [];
  const emails = [];
  const seen = new Set();

  for (const match of matches) {
    const email = tclabNormalizeEmail(match);
    if (!email || TCLAB_FAKE_EMAILS.has(email) || seen.has(email)) {
      continue;
    }
    seen.add(email);
    emails.push(email);
  }

  return emails;
}

function tclabNormalizeEmail(value) {
  const email = value
    .trim()
    .replace(/^[<("'`[{]+/g, '')
    .replace(/[>,.;:'"`)\]}]+$/g, '')
    .toLowerCase();

  return TCLAB_EMAIL_VALIDATION_REGEX.test(email) ? email : '';
}

function tclabCollectExternalLinks() {
  const links = Array.from(document.querySelectorAll('a[href]'));
  const output = [];
  const seen = new Set();

  for (const link of links) {
    if (!tclabIsVisible(link)) {
      continue;
    }

    const href = (link.href || '').trim();
    if (!href || href.startsWith('javascript:') || href.startsWith('#')) {
      continue;
    }

    const lowerHref = href.toLowerCase();
    if (lowerHref.startsWith('mailto:')) {
      if (!seen.has(href)) {
        seen.add(href);
        output.push(href);
      }
      continue;
    }

    let url;
    try {
      url = new URL(href);
    } catch {
      continue;
    }

    if (!['http:', 'https:'].includes(url.protocol)) {
      continue;
    }

    const hostname = url.hostname.replace(/^www\./i, '').toLowerCase();
    if (TCLAB_BLOCKED_EXTERNAL_DOMAINS.has(hostname)) {
      continue;
    }

    const isUsefulKnownDomain = TCLAB_USEFUL_EXTERNAL_DOMAINS.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`));
    const finalUrl = url.toString();
    if ((isUsefulKnownDomain || hostname) && !seen.has(finalUrl)) {
      seen.add(finalUrl);
      output.push(finalUrl);
    }
  }

  return output;
}

function tclabTextFromSelectors(selectors) {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    const text = element?.innerText?.trim();
    if (text) {
      return text;
    }
  }
  return '';
}

function tclabExtractMetric(text, labels) {
  const compactNumber = '(\\d+(?:[,.]\\d+)*(?:\\.\\d+)?\\s*[KMB]?)';
  for (const label of labels) {
    const beforeLabel = new RegExp(`${compactNumber}\\s+${label}\\b`, 'i');
    const afterLabel = new RegExp(`\\b${label}\\s+${compactNumber}`, 'i');
    const beforeMatch = text.match(beforeLabel);
    if (beforeMatch?.[1]) {
      return tclabNormalizeWhitespace(beforeMatch[1]);
    }
    const afterMatch = text.match(afterLabel);
    if (afterMatch?.[1]) {
      return tclabNormalizeWhitespace(afterMatch[1]);
    }
  }
  return '';
}

function tclabGuessBio(text) {
  const lines = text.split('\n').map((line) => line.trim()).filter(Boolean);
  return lines.find((line) => {
    if (line.length < 4 || line.length > 500) {
      return false;
    }
    if (/^(following|followers?|likes?|videos?|liked|message|follow)$/i.test(line)) {
      return false;
    }
    if (/^\d+(?:[,.]\d+)*(?:\.\d+)?\s*[KMB]?$/i.test(line)) {
      return false;
    }
    return line.includes('@') || line.includes('.') || line.split(/\s+/).length >= 3;
  }) || '';
}

function tclabParseCompactNumber(rawValue) {
  const cleaned = String(rawValue || '').replace(/,/g, '').trim();
  const match = cleaned.match(/^(\d+(?:\.\d+)?)\s*([KMB])?$/i);
  if (!match) {
    return null;
  }

  const value = Number.parseFloat(match[1]);
  if (Number.isNaN(value)) {
    return null;
  }

  const suffix = match[2]?.toUpperCase();
  const multiplier = suffix === 'K' ? 1000 : suffix === 'M' ? 1000000 : suffix === 'B' ? 1000000000 : 1;
  return Math.round(value * multiplier);
}

function tclabExtractUsername(value) {
  const match = String(value || '').match(/\/@([^/?#]+)(?:\/|$)/i);
  return match?.[1] ? decodeURIComponent(match[1]).trim() : '';
}

function tclabGetVideoIdentityKey(value) {
  const match = String(value || '').match(/\/@([^/?#]+)\/video\/(\d+)/i);
  if (!match?.[1] || !match?.[2]) {
    return '';
  }

  return `${decodeURIComponent(match[1]).trim().toLowerCase()}/video/${match[2]}`;
}

function tclabInferSearchKeyword(value) {
  try {
    const url = new URL(value);
    return url.searchParams.get('q') || '';
  } catch {
    return '';
  }
}

function tclabCanonicalUrl(value) {
  try {
    const url = new URL(value);
    url.hash = '';
    return url.toString();
  } catch {
    return String(value || '').trim();
  }
}

function tclabIsVisible(element) {
  const style = window.getComputedStyle(element);
  return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0;
}

function tclabNormalizeWhitespace(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function tclabNormalizeSearchText(value) {
  return tclabNormalizeWhitespace(value).toLowerCase();
}

function tclabTruncate(value, maxLength) {
  const normalized = tclabNormalizeWhitespace(value);
  return normalized.length > maxLength ? `${normalized.slice(0, Math.max(0, maxLength - 3))}...` : normalized;
}

function tclabHashText(value) {
  const text = String(value || '');
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

function tclabClampNumber(value, min, max, fallback) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  return Math.min(max, Math.max(min, parsed));
}

function tclabSleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
})();
