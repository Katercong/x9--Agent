importScripts("youtube_config.js", "youtube_utils.js", "youtube_review_queue.js");

const STORE_KEY = "x9_youtube_preview_state";
const ACTOR_CONFIG_KEY = "x9_youtube_actor_config_override";
const LAST_HEARTBEAT_KEY = "x9_youtube_last_heartbeat";
const STABLE_WORKER_ID_KEY = "x9_youtube_stable_worker_id";
const HEARTBEAT_STALE_MS = 60_000;
const YOUTUBE_IMPORT_BASE_URL = getX9YoutubeBackendBaseUrl();
const YOUTUBE_IDENTITY_BASE_URL = getX9YoutubeIdentityBaseUrl();

const MSG = {
  PANEL_START: "X9_YOUTUBE_PANEL_START",
  PANEL_START_SEARCH: "X9_YOUTUBE_PANEL_START_SEARCH",
  PANEL_CONTINUE_SEARCH: "X9_YOUTUBE_PANEL_CONTINUE_SEARCH",
  PANEL_OPEN_NEXT_MANUAL_REVIEW: "X9_YOUTUBE_PANEL_OPEN_NEXT_MANUAL_REVIEW",
  PANEL_COLLECT_CURRENT_PAGE_EMAIL: "X9_YOUTUBE_PANEL_COLLECT_CURRENT_PAGE_EMAIL",
  PANEL_BIND_ACTOR: "X9_YOUTUBE_PANEL_BIND_ACTOR",
  PANEL_OPEN_LOGIN: "X9_YOUTUBE_PANEL_OPEN_LOGIN",
  PANEL_STOP: "X9_YOUTUBE_PANEL_STOP",
  PANEL_GET_STATE: "X9_YOUTUBE_PANEL_GET_STATE",
  PANEL_CLEAR: "X9_YOUTUBE_PANEL_CLEAR",
  CONTENT_PING: "X9_YOUTUBE_PING",
  CONTENT_COLLECT: "X9_YOUTUBE_COLLECT",
  CONTENT_COLLECT_SEARCH: "X9_YOUTUBE_COLLECT_SEARCH",
  CONTENT_COLLECT_PROFILE: "X9_YOUTUBE_COLLECT_PROFILE",
  CONTENT_COLLECT_CHANNEL_VIDEOS: "X9_YOUTUBE_COLLECT_CHANNEL_VIDEOS",
  CONTENT_STOP: "X9_YOUTUBE_STOP"
};

let stopRequested = false;
let stableWorkerIdentityPromise = null;
let actorConfigCache = null;
let actorHeartbeatPromise = null;

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => undefined);
  ensureInitialState();
});

chrome.runtime.onStartup?.addListener(() => {
  ensureInitialState();
});

chrome.action.onClicked.addListener((tab) => {
  if (tab?.windowId) {
    chrome.sidePanel?.open?.({ windowId: tab.windowId }).catch(() => undefined);
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message.type !== "string") return false;

  (async () => {
    if (message.type === MSG.PANEL_GET_STATE) {
      const state = await stateWithActorIdentity({ heartbeatIfStale: true });
      sendResponse({ ok: true, state });
      return;
    }
    if (message.type === MSG.PANEL_CLEAR) {
      const state = defaultState();
      await setState(state);
      sendResponse({ ok: true, state: await stateWithActorIdentity({ heartbeatIfStale: false }) });
      return;
    }
    if (message.type === MSG.PANEL_BIND_ACTOR) {
      sendResponse(await bindYoutubeActorFromLogin());
      return;
    }
    if (message.type === MSG.PANEL_OPEN_LOGIN) {
      sendResponse(await openYoutubeIdentityLogin());
      return;
    }
    if (message.type === MSG.PANEL_STOP) {
      sendResponse(await stopActiveRun());
      return;
    }
    if (message.type === MSG.PANEL_OPEN_NEXT_MANUAL_REVIEW) {
      sendResponse(await openNextManualReview());
      return;
    }
    if (message.type === MSG.PANEL_COLLECT_CURRENT_PAGE_EMAIL) {
      sendResponse(await collectCurrentPageEmail());
      return;
    }
    if (message.type === MSG.PANEL_CONTINUE_SEARCH) {
      sendResponse(await startCurrentSearchPageRun(message.settings || {}, { continueRun: true }));
      return;
    }
    if (message.type === MSG.PANEL_START_SEARCH || message.type === MSG.PANEL_START) {
      sendResponse(await startCurrentSearchPageRun(message.settings || {}));
      return;
    }
    sendResponse({ ok: false, error: "unknown_message" });
  })().catch((error) => {
    sendResponse({ ok: false, error: errorText(error) });
  });

  return true;
});

async function startCurrentSearchPageRun(rawSettings, options = {}) {
  const actorGuard = await requireYoutubeActorVerified();
  if (!actorGuard.ok) {
    const state = {
      ...(await getState()),
      status: "error",
      message: actorGuard.message,
      actor_identity: actorGuard.identity
    };
    await setState(state);
    return { ok: false, error: actorGuard.error, state };
  }

  const activeTab = await getActiveTab();
  if (!activeTab?.id || !isYoutubeSearchResultsUrl(activeTab.url || "")) {
    return {
      ok: false,
      error: "active_tab_is_not_youtube_search_results",
      message: "Open a YouTube search results page first, then start collection."
    };
  }

  const previousState = await getState();
  if (previousState.worker_tab_id && previousState.worker_tab_id !== activeTab.id) {
    await closeWorkerTab(previousState.worker_tab_id, activeTab.id).catch(() => undefined);
  }

  const settings = normalizeSettings({
    ...rawSettings,
    keyword: extractSearchKeyword(activeTab.url || "") || rawSettings.keyword || ""
  });
  if (!settings.collectCreators && !settings.collectCommenters) {
    const state = {
      ...(await getState()),
      status: "error",
      message: "Select at least one collection target.",
      settings
    };
    await setState(state);
    return { ok: false, error: "no_collection_targets_selected", state };
  }
  const continueRun = Boolean(options.continueRun);
  const storedRows = getStoredRows(previousState);
  const storedVideos = getStoredVideos(previousState);
  const hasPreviousCollection = Boolean(storedRows.length || storedVideos.length);
  const previousSourceSearchUrl = previousState.result?.source_search_url || "";
  const previousKeyword = previousState.keyword || previousState.settings?.keyword || "";
  const sameSearchScope = hasPreviousCollection && isSameSearchScope(previousSourceSearchUrl, activeTab.url || "", previousKeyword, settings.keyword);
  const carryPreviousCollection = hasPreviousCollection && (continueRun || sameSearchScope);
  const previousRows = carryPreviousCollection ? storedRows : [];
  const previousVideos = carryPreviousCollection ? storedVideos : [];
  const previousCounts = carryPreviousCollection ? (previousState.counts || previousState.result?.counts || {}) : {};
  const previousIncrementalUpload = carryPreviousCollection ? previousState.incremental_upload : null;
  if (continueRun && !hasPreviousCollection) {
    const state = {
      ...previousState,
      status: "error",
      message: "No previous collection to continue. Click Start first."
    };
    await setState(state);
    return { ok: false, error: "no_previous_collection_to_continue", state };
  }

  stopRequested = false;
  const runId = `yt-manual-search-${Date.now()}`;
  const startedAt = new Date().toISOString();
  await setState({
    ...defaultState(),
    actor_identity: actorGuard.identity,
    mode: "manual_search_results",
    run_id: runId,
    status: "running",
    message: carryPreviousCollection ? "Continuing from previous results..." : "Collecting from current YouTube search results page...",
    keyword: settings.keyword,
    settings,
    active_tab_id: activeTab.id,
    rows: previousRows,
    manual_review_rows: carryPreviousCollection ? buildManualReviewRows(previousRows) : [],
    videos: previousVideos,
    counts: carryPreviousCollection
      ? makeCounts(previousVideos.length, Number(previousCounts.comments || 0), Number(previousCounts.profile_pages || 0), previousRows, buildManualReviewRows(previousRows))
      : {},
    incremental_upload: normalizeIncrementalUpload(previousIncrementalUpload),
    worker_tab_id: null,
    started_at: startedAt,
    logs: []
  });

  let workerSession = null;
  try {
    const knownEmails = buildKnownEmailSet(previousRows);
    await loadHistoricalKnownEmails(knownEmails);
    await ensureContentScript(activeTab.id);
    const previousVideoKeys = buildCollectedVideoKeySet(previousRows, previousVideos);
    const searchSettings = carryPreviousCollection
      ? {
          ...settings,
          maxVideos: Math.min(100, Math.max(settings.maxVideos, settings.maxVideos + previousVideoKeys.size))
        }
      : settings;
    const searchResponse = await sendTabMessage(activeTab.id, {
      type: MSG.CONTENT_COLLECT_SEARCH,
      settings: searchSettings
    });
    if (!searchResponse?.ok) throw new Error(searchResponse?.error || "search_collect_failed");

    const searchResult = searchResponse.result || {};
    const currentSourceSearchUrl = searchResult.page_url || activeTab.url || "";
    if (continueRun && !isSameSearchScope(previousSourceSearchUrl, currentSourceSearchUrl, previousKeyword, settings.keyword)) {
      const state = {
        ...previousState,
        status: "error",
        message: "Continue only works on the same YouTube search results page. Click Start or Clear first."
      };
      await setState(state);
      return { ok: false, error: "continue_search_scope_mismatch", state };
    }

    const allVideos = searchResult.videos || [];
    const skippedCount = carryPreviousCollection ? allVideos.filter((video) => hasCollectedVideo(previousVideoKeys, video)).length : 0;
    const videos = allVideos
      .filter((video) => !carryPreviousCollection || !hasCollectedVideo(previousVideoKeys, video))
      .slice(0, settings.maxVideos);
    const rows = previousRows.slice();
    const videosOut = previousVideos.slice();
    const profileCache = new Map();
    const commenterProfileCache = new Map();
    const collectedCommenterKeys = buildCollectedCommenterKeySet(rows);
    let profilePages = continueRun ? Number(previousCounts.profile_pages || 0) : 0;
    let commentsCount = continueRun ? Number(previousCounts.comments || 0) : 0;

    if (!videos.length) {
      if (!carryPreviousCollection) throw new Error("no_search_videos_found");
      const manualReviewRows = buildManualReviewRows(rows);
      const state = {
        ...(await getState()),
        status: "done",
        message: "No new videos found on this search page. Scroll the search page further or increase search scroll rounds.",
        result: {
          keyword: settings.keyword,
          source_search_url: currentSourceSearchUrl,
          videos: videosOut,
          rows,
          manual_review_rows: manualReviewRows,
          counts: makeCounts(videosOut.length, commentsCount, profilePages, rows, manualReviewRows),
          collected_at: new Date().toISOString()
        },
        rows,
        manual_review_rows: manualReviewRows,
        videos: videosOut,
        counts: makeCounts(videosOut.length, commentsCount, profilePages, rows, manualReviewRows),
        worker_tab_id: null,
        finished_at: new Date().toISOString()
      };
      await setState(state);
      return { ok: true, state };
    }
    await addLog(
      "search_results",
      carryPreviousCollection
        ? `Skipped ${skippedCount} previously collected videos. Continuing with ${videos.length} new videos.`
        : `Found ${videos.length} videos on current page`
    );

    for (let index = 0; index < videos.length && !stopRequested; index += 1) {
      const videoCard = videos[index];
      workerSession = createWorkerSession(activeTab);
      try {
        const shouldCollectCommenters = Boolean(settings.collectCommenters);
        const maxCommentsForRun = shouldCollectCommenters ? settings.maxCommentsPerVideo : 0;
        const maxCommenterProfilesForRun = shouldCollectCommenters ? settings.maxCommenterProfilesPerVideo : 0;
        await patchState({ message: `Opening video in active tab ${index + 1}/${videos.length}: ${videoCard.video_title || videoCard.video_id}` });
        const workerTab = await openWorkerTab(workerSession, videoCard.video_url);
        await patchState({ worker_tab_id: workerTab.id });
        await waitForTabComplete(workerTab.id, 60_000);
        await ensureContentScript(workerTab.id);
        await sleep(1000);

        const videoResponse = await sendTabMessage(workerTab.id, {
          type: MSG.CONTENT_COLLECT,
          settings: {
            ...settings,
            maxComments: maxCommentsForRun,
            maxCommenterProfiles: maxCommenterProfilesForRun,
            scrollRounds: settings.scrollRounds
          }
        });
        if (!videoResponse?.ok) {
          await addLog("video_error", `${videoCard.video_url} | ${videoResponse?.error || "unknown"}`);
          continue;
        }

        const videoResult = videoResponse.result || {};
        const video = videoResult.video || videoCard;
        const creatorChannelUrl = videoResult.channel?.channel_url || videoCard.creator_channel_url || "";
        const videoComments = shouldCollectCommenters && Array.isArray(videoResult.comments) ? videoResult.comments : [];
        const commenterComments = shouldCollectCommenters
          ? uniqueCommenterChannels(videoComments).slice(0, settings.maxCommenterProfilesPerVideo)
          : [];
        commentsCount += videoComments.length;
        videosOut.push({
          ...videoCard,
          video,
          channel: videoResult.channel,
          comments_count: videoComments.length,
          commenter_profiles_count: commenterComments.length
        });
        addCollectedVideo(previousVideoKeys, videoCard);
        addCollectedVideo(previousVideoKeys, video);

        const creatorVideoEmail = videoEmailResult(video, "video_description");
        let creatorProfile = emptyProfile(creatorChannelUrl);
        if (!hasEmails(creatorVideoEmail) && creatorChannelUrl) {
          creatorProfile = await collectProfileWithCache(profileCache, creatorChannelUrl, activeTab.id, settings, "creator", {
            fallbackToFirstVideo: false,
            workerSession
          });
          profilePages += creatorProfile.from_cache ? 0 : (creatorProfile.profile_pages_checked || 0);
        }
        await appendCollectedRow(buildCreatorRow(settings, video, creatorChannelUrl, creatorVideoEmail, creatorProfile), {
          rows,
          videosOut,
          knownEmails,
          settings,
          sourceSearchUrl: currentSourceSearchUrl,
          buildPatch: () => {
            const manualReviewRows = buildManualReviewRows(rows);
            return {
              rows,
              manual_review_rows: manualReviewRows,
              videos: videosOut,
              counts: makeCounts(videosOut.length, commentsCount, profilePages, rows, manualReviewRows)
            };
          }
        });
        await addLog(
          "creator_checked",
          `${creatorChannelUrl || "missing_channel"} | video_email=${creatorVideoEmail.email || ""} profile_email=${creatorProfile.email || ""}`
        );
        await sleep(settings.betweenProfilesMs);

        if (shouldCollectCommenters) {
          await addLog("comments_collected", `${video.video_url || videoCard.video_url} | comments=${videoComments.length} commenters=${commenterComments.length}`);
          for (const comment of commenterComments) {
            if (stopRequested) break;
            const commenterChannelUrl = X9YoutubeUtils.normalizeChannelUrl(comment.author_channel_url || "");
            if (!commenterChannelUrl || collectedCommenterKeys.has(commenterChannelUrl)) continue;
            await patchState({ message: `Checking commenter About: ${comment.author_name || commenterChannelUrl}` });
            const commenterProfile = await collectCommenterAboutProfile(commenterProfileCache, commenterChannelUrl, activeTab.id, settings, workerSession);
            profilePages += commenterProfile.from_cache ? 0 : (commenterProfile.profile_pages_checked || 0);
            const rowResult = await appendCollectedRow(buildCommenterRow(settings, video, creatorChannelUrl, { ...comment, author_channel_url: commenterChannelUrl }, commenterProfile), {
              rows,
              videosOut,
              knownEmails,
              settings,
              sourceSearchUrl: currentSourceSearchUrl,
              buildPatch: () => {
                const manualReviewRows = buildManualReviewRows(rows);
                return {
                  rows,
                  manual_review_rows: manualReviewRows,
                  videos: videosOut,
                  counts: makeCounts(videosOut.length, commentsCount, profilePages, rows, manualReviewRows)
                };
              }
            });
            if (rowResult.added || rowResult.skipped_duplicate) collectedCommenterKeys.add(commenterChannelUrl);
            await sleep(settings.betweenProfilesMs);
          }
        } else {
          await addLog("comments_skipped", `${video.video_url || videoCard.video_url} | commenter collection disabled`);
        }
      } finally {
        await closeWorkerSession(workerSession, activeTab.id);
        workerSession = null;
        await activateSearchTab(activeTab.id);
        await patchState({ worker_tab_id: null });
        if (!stopRequested) await sleep(1000);
      }
    }

    await activateSearchTab(activeTab.id);
    const manualReviewRows = buildManualReviewRows(rows);
    const finalState = {
      ...(await getState()),
      status: stopRequested ? "stopped" : "done",
      message: stopRequested ? "Stopped." : "Manual search page collection complete.",
      keyword: settings.keyword,
      result: {
        keyword: settings.keyword,
        source_search_url: searchResult.page_url || activeTab.url || "",
        videos: videosOut,
        rows,
        manual_review_rows: manualReviewRows,
        counts: makeCounts(videosOut.length, commentsCount, profilePages, rows, manualReviewRows),
        collected_at: new Date().toISOString()
      },
      rows,
      manual_review_rows: manualReviewRows,
      counts: makeCounts(videosOut.length, commentsCount, profilePages, rows, manualReviewRows),
      worker_tab_id: null,
      finished_at: new Date().toISOString()
    };
    await setState(finalState);
    return { ok: true, state: finalState };
  } catch (error) {
    const currentState = await getState();
    await closeWorkerSession(workerSession, activeTab.id);
    await closeWorkerTab(currentState.worker_tab_id, activeTab.id);
    await activateSearchTab(activeTab.id);
    workerSession = null;
    const state = {
      ...(await getState()),
      status: stopRequested ? "stopped" : "error",
      message: stopRequested ? "Stopped." : errorText(error),
      worker_tab_id: null,
      finished_at: new Date().toISOString()
    };
    await setState(state);
    return { ok: false, error: errorText(error), state };
  }
}

async function collectProfileWithCache(cache, channelUrl, openerTabId, settings, role, options = {}) {
  const normalized = X9YoutubeUtils.normalizeChannelUrl(channelUrl);
  if (!normalized) return emptyProfile(channelUrl);
  const cached = cache.get(normalized);
  if (cached && (!options.fallbackToFirstVideo || hasEmailValue(cached) || cached.fallback_video_checked)) {
    return { ...cached, from_cache: true };
  }

  let profile = cached || await collectChannelProfile(normalized, openerTabId, settings, role, options.workerSession);
  if (options.fallbackToFirstVideo && !hasEmailValue(profile) && !profile.fallback_video_checked) {
    profile = await collectFirstPublicVideoEmail(profile, normalized, openerTabId, settings, options.workerSession);
  }
  cache.set(normalized, profile);
  return profile;
}

async function collectCommenterAboutProfile(cache, channelUrl, openerTabId, settings, workerSession) {
  const normalized = X9YoutubeUtils.normalizeChannelUrl(channelUrl);
  if (!normalized) return emptyProfile(channelUrl);
  const cacheKey = `comment_author_about:${normalized}`;
  const cached = cache.get(cacheKey);
  if (cached) return { ...cached, from_cache: true };

  const profile = await collectProfilePageAt({
    channelUrl: normalized,
    openerTabId,
    settings,
    role: "comment_author",
    url: X9YoutubeUtils.channelAboutUrl(normalized),
    source: "comment_author_channel_about",
    pageType: "about",
    workerSession
  });
  cache.set(cacheKey, profile);
  return profile;
}

async function collectChannelProfile(channelUrl, openerTabId, settings, role, workerSession) {
  let profile = await collectProfilePageAt({
    channelUrl,
    openerTabId,
    settings,
    role,
    url: X9YoutubeUtils.channelHomeUrl(channelUrl),
    source: `${role}_channel_home`,
    pageType: "home",
    workerSession
  });
  if (!hasEmailValue(profile)) {
    const aboutProfile = await collectProfilePageAt({
      channelUrl,
      openerTabId,
      settings,
      role,
      url: X9YoutubeUtils.channelAboutUrl(channelUrl),
      source: `${role}_channel_about`,
      pageType: "about",
      workerSession
    });
    profile = mergeProfiles(profile, aboutProfile);
  }
  return profile;
}

async function collectProfilePageAt({ channelUrl, openerTabId, settings, role, url, source, pageType, workerSession }) {
  const { tab: profileTab, shouldClose } = await openCollectionTab(workerSession, url);
  try {
    await waitForTabComplete(profileTab.id, 45_000);
    await ensureContentScript(profileTab.id);
    await sleep(settings.profileSettleMs);
    const response = await sendTabMessage(profileTab.id, {
      type: MSG.CONTENT_COLLECT_PROFILE,
      settings: {
        ...settings,
        openAboutDialog: pageType === "about"
      }
    });
    if (!response?.ok) throw new Error(response?.error || "profile_collect_failed");
    const result = response.result || emptyProfile(channelUrl);
    return {
      ...result,
      role,
      source_channel_url: channelUrl,
      email_source: result.email ? source : "",
      checked_profile_url: url,
      checked_channel_home_url: pageType === "home" ? url : "",
      checked_about_url: pageType === "about" ? url : "",
      checked_video_url: "",
      hidden_email_button_present: Boolean(result.hidden_email_button_present),
      captcha_required: Boolean(result.captcha_required),
      fallback_video_checked: false,
      profile_pages_checked: 1
    };
  } catch (error) {
    return {
      ...emptyProfile(channelUrl),
      role,
      error: errorText(error),
      source_channel_url: channelUrl,
      checked_profile_url: url,
      checked_channel_home_url: pageType === "home" ? url : "",
      checked_about_url: pageType === "about" ? url : "",
      hidden_email_button_present: false,
      captcha_required: false,
      fallback_video_checked: false,
      profile_pages_checked: 1
    };
  } finally {
    if (shouldClose && profileTab?.id && profileTab.id !== openerTabId) {
      await chrome.tabs.remove(profileTab.id).catch(() => undefined);
    }
  }
}

function mergeProfiles(primary, fallback) {
  const emailProfile = hasEmailValue(primary) ? primary : fallback;
  return {
    ...primary,
    email: emailProfile.email || "",
    emails: mergeEmails(primary.emails, fallback.emails),
    contacts: [...(primary.contacts || []), ...(fallback.contacts || [])],
    external_links: mergeStrings(primary.external_links, fallback.external_links),
    profile_text: [primary.profile_text, fallback.profile_text].filter(Boolean).join("\n"),
    page_url: emailProfile.page_url || fallback.page_url || primary.page_url || "",
    checked_profile_url: emailProfile.checked_profile_url || fallback.checked_profile_url || primary.checked_profile_url || "",
    checked_channel_home_url: primary.checked_channel_home_url || fallback.checked_channel_home_url || "",
    checked_about_url: primary.checked_about_url || fallback.checked_about_url || "",
    hidden_email_button_present: Boolean(primary.hidden_email_button_present || fallback.hidden_email_button_present),
    captcha_required: Boolean(primary.captcha_required || fallback.captcha_required),
    email_source: emailProfile.email_source || "",
    fallback_video_checked: false,
    profile_pages_checked: (primary.profile_pages_checked || 0) + (fallback.profile_pages_checked || 0),
    error: [primary.error, fallback.error].filter(Boolean).join(" | ")
  };
}

function mergeStrings(...groups) {
  const seen = new Set();
  const values = [];
  for (const group of groups) {
    const items = Array.isArray(group) ? group : [];
    for (const raw of items) {
      const value = String(raw || "").trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      values.push(value);
    }
  }
  return values;
}

async function collectFirstPublicVideoEmail(profile, channelUrl, openerTabId, settings, workerSession) {
  const collectionTab = await openCollectionTab(workerSession, X9YoutubeUtils.channelVideosUrl(channelUrl));
  let videoTab = collectionTab.tab;
  try {
    await waitForTabComplete(videoTab.id, 45_000);
    await ensureContentScript(videoTab.id);
    await sleep(settings.profileSettleMs);
    const videosResponse = await sendTabMessage(videoTab.id, {
      type: MSG.CONTENT_COLLECT_CHANNEL_VIDEOS,
      settings
    });
    const firstVideo = videosResponse?.ok ? (videosResponse.result?.videos || [])[0] : null;
    if (!firstVideo?.video_url) {
      return {
        ...profile,
        fallback_video_checked: true,
        checked_video_url: "",
        manual_review_url: profile.page_url || X9YoutubeUtils.channelAboutUrl(channelUrl)
      };
    }

    videoTab = await navigateCollectionTab(collectionTab, workerSession, firstVideo.video_url);
    await waitForTabComplete(videoTab.id, 60_000);
    await ensureContentScript(videoTab.id);
    await sleep(1000);
    const videoResponse = await sendTabMessage(videoTab.id, {
      type: MSG.CONTENT_COLLECT,
      settings: {
        ...settings,
        maxComments: 1,
        scrollRounds: 0
      }
    });
    const video = videoResponse?.ok ? videoResponse.result?.video : null;
    const fallback = videoEmailResult(video || firstVideo, "comment_author_video_description");
    return {
      ...profile,
      email: profile.email || fallback.email || "",
      emails: mergeEmails(profile.emails, fallback.emails),
      email_source: profile.email_source || (fallback.email ? "comment_author_video_description" : ""),
      checked_video_url: firstVideo.video_url,
      video_detail_text: fallback.video_detail_text || "",
      video_email_evidence_url: fallback.evidence_url || "",
      fallback_video_checked: true,
      manual_review_url: fallback.email ? "" : (firstVideo.video_url || profile.page_url || X9YoutubeUtils.channelAboutUrl(channelUrl))
    };
  } catch (error) {
    return {
      ...profile,
      fallback_video_checked: true,
      checked_video_url: "",
      error: profile.error || errorText(error),
      manual_review_url: profile.page_url || X9YoutubeUtils.channelAboutUrl(channelUrl)
    };
  } finally {
    if (collectionTab.shouldClose && videoTab?.id && videoTab.id !== openerTabId) {
      await chrome.tabs.remove(videoTab.id).catch(() => undefined);
    }
  }
}

function buildCreatorRow(settings, video, creatorChannelUrl, videoEmail, profile) {
  const chosen = hasEmails(videoEmail)
    ? videoEmail
    : profileEmailResult(profile, "");
  const checkedProfileUrl = hasEmails(videoEmail) ? "" : (profile.checked_profile_url || profile.page_url || X9YoutubeUtils.channelAboutUrl(creatorChannelUrl));
  const needsVerificationReview = !hasEmails(chosen) && Boolean(profile.hidden_email_button_present || profile.captcha_required);
  return baseRow({
    settings,
    sourceType: "creator_channel",
    video,
    creatorChannelUrl,
    emailResult: chosen,
    checkedProfileUrl,
    checkedChannelHomeUrl: hasEmails(videoEmail) ? "" : (profile.checked_channel_home_url || X9YoutubeUtils.channelHomeUrl(creatorChannelUrl)),
    checkedAboutUrl: hasEmails(videoEmail) ? "" : (profile.checked_about_url || ""),
    checkedVideoUrl: video.video_url || "",
    manualReviewUrl: needsVerificationReview ? checkedProfileUrl : "",
    profileText: profile.profile_text || "",
    videoDetailText: video.video_detail_text || video.description || "",
    hiddenEmailButtonPresent: !hasEmails(chosen) && Boolean(profile.hidden_email_button_present),
    captchaRequired: !hasEmails(chosen) && Boolean(profile.captcha_required)
  });
}

function buildCommenterRow(settings, video, creatorChannelUrl, comment, profile) {
  const chosen = profileEmailResult(profile, profile.email_source || "");
  const needsVerificationReview = !hasEmails(chosen) && Boolean(profile.hidden_email_button_present || profile.captcha_required);
  const manualReviewUrl = needsVerificationReview
    ? (profile.manual_review_url || profile.checked_video_url || profile.checked_profile_url || profile.page_url || comment.author_channel_url || "")
    : "";
  return baseRow({
    settings,
    sourceType: "comment_author_channel",
    video,
    creatorChannelUrl,
    comment,
    emailResult: chosen,
    checkedProfileUrl: profile.checked_profile_url || profile.page_url || X9YoutubeUtils.channelAboutUrl(comment.author_channel_url),
    checkedChannelHomeUrl: "",
    checkedAboutUrl: profile.checked_about_url || "",
    checkedVideoUrl: "",
    manualReviewUrl,
    profileText: profile.profile_text || "",
    videoDetailText: profile.video_detail_text || "",
    hiddenEmailButtonPresent: !hasEmails(chosen) && Boolean(profile.hidden_email_button_present),
    captchaRequired: !hasEmails(chosen) && Boolean(profile.captcha_required)
  });
}

function baseRow({ settings, sourceType, video, creatorChannelUrl, comment = {}, emailResult, checkedProfileUrl, checkedChannelHomeUrl, checkedAboutUrl, checkedVideoUrl, manualReviewUrl, profileText, videoDetailText, hiddenEmailButtonPresent = false, captchaRequired = false }) {
  const emails = Array.isArray(emailResult?.emails) ? emailResult.emails : [];
  const email = emails[0] || emailResult?.email || "";
  const needsVerificationReview = !email && Boolean(hiddenEmailButtonPresent || captchaRequired || manualReviewUrl);
  return {
    source_type: sourceType,
    keyword: settings.keyword || "",
    video_id: video.video_id || X9YoutubeUtils.extractVideoId(video.video_url || ""),
    content_type: video.content_type || X9YoutubeUtils.detectContentType(video.video_url || checkedVideoUrl || "") || "video",
    video_title: video.title || video.video_title || "",
    video_url: video.video_url || "",
    creator_channel_url: creatorChannelUrl || "",
    comment_author_name: comment.author_name || "",
    comment_author_channel_url: comment.author_channel_url || "",
    email,
    emails_json: JSON.stringify(emails),
    email_source: email ? (emailResult?.email_source || "") : "",
    evidence_url: email ? (emailResult?.evidence_url || checkedProfileUrl || checkedVideoUrl || video.video_url || "") : "",
    manual_review_url: needsVerificationReview ? (manualReviewUrl || checkedVideoUrl || checkedProfileUrl || comment.author_channel_url || creatorChannelUrl || "") : "",
    hidden_email_button_present: Boolean(hiddenEmailButtonPresent),
    captcha_required: Boolean(captchaRequired),
    review_reason: "",
    checked_profile_url: checkedProfileUrl || "",
    checked_channel_home_url: checkedChannelHomeUrl || "",
    checked_about_url: checkedAboutUrl || "",
    checked_video_url: checkedVideoUrl || "",
    profile_text: profileText || "",
    video_detail_text: videoDetailText || "",
    needs_manual_review: needsVerificationReview,
    collected_at: new Date().toISOString()
  };
}

function videoEmailResult(video, emailSource) {
  const emails = mergeEmails(video?.emails, []);
  return {
    email: emails[0] || "",
    emails,
    email_source: emails.length ? emailSource : "",
    evidence_url: emails.length ? (video?.video_url || "") : "",
    video_detail_text: video?.video_detail_text || video?.description || ""
  };
}

function profileEmailResult(profile, emailSource) {
  const emails = mergeEmails(profile?.emails, profile?.email ? [profile.email] : []);
  const fallbackVideoSource = profile?.email_source === "comment_author_video_description";
  return {
    email: emails[0] || "",
    emails,
    email_source: emails.length ? (profile?.email_source || emailSource) : "",
    evidence_url: emails.length
      ? (fallbackVideoSource ? profile?.video_email_evidence_url || profile?.checked_video_url : profile?.page_url || profile?.checked_profile_url)
      : "",
    video_detail_text: profile?.video_detail_text || ""
  };
}

function hasEmails(result) {
  return Boolean(result?.email || (Array.isArray(result?.emails) && result.emails.length));
}

function hasEmailValue(profile) {
  return Boolean(profile?.email || (Array.isArray(profile?.emails) && profile.emails.length));
}

function mergeEmails(...groups) {
  const seen = new Set();
  const emails = [];
  for (const group of groups) {
    const items = Array.isArray(group) ? group : [];
    for (const raw of items) {
      const email = String(raw || "").trim().toLowerCase();
      if (!email || seen.has(email)) continue;
      seen.add(email);
      emails.push(email);
    }
  }
  return emails;
}

function rowEmailValues(row) {
  const values = [];
  if (row?.email) values.push(row.email);
  for (const raw of parseJsonList(row?.emails_json)) values.push(raw);
  for (const raw of parseJsonList(row?.emails)) values.push(raw);
  return mergeEmails(values);
}

function parseJsonList(value) {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  try {
    const parsed = JSON.parse(String(value));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function buildKnownEmailSet(rows) {
  const emails = new Set();
  for (const row of rows || []) {
    for (const email of rowEmailValues(row)) emails.add(email);
  }
  return emails;
}

function rememberRowEmails(row, knownEmails) {
  for (const email of rowEmailValues(row)) knownEmails.add(email);
}

function duplicateRowEmail(row, knownEmails) {
  return rowEmailValues(row).find((email) => knownEmails.has(email)) || "";
}

function isImportableRow(row) {
  if (rowEmailValues(row).length) return true;
  const reasons = X9YoutubeReviewQueue.reviewReasons(row) || [];
  return Array.isArray(reasons) && reasons.length > 0;
}

async function appendCollectedRow(row, context) {
  const duplicateEmail = duplicateRowEmail(row, context.knownEmails);
  if (duplicateEmail) {
    await patchIncrementalUpload((upload) => ({
      ...upload,
      status: "skipped_duplicate",
      skipped_duplicates: upload.skipped_duplicates + 1,
      last_duplicate_email: duplicateEmail,
      last_error: ""
    }));
    await addLog("duplicate_email_skipped", `${duplicateEmail} | ${row.creator_channel_url || row.comment_author_channel_url || ""}`);
    await patchState(context.buildPatch());
    return { added: false, skipped_duplicate: true };
  }

  context.rows.push(row);
  await patchState(context.buildPatch());

  if (!isImportableRow(row)) {
    return { added: true, uploaded: false };
  }

  const result = await uploadYoutubeRow(row, context);
  if (result.ok) rememberRowEmails(row, context.knownEmails);
  return { added: true, uploaded: result.ok };
}

async function stateWithActorIdentity(options = {}) {
  const identity = await refreshYoutubeActorIdentity(options);
  return {
    ...(await getState()),
    actor_identity: identity
  };
}

async function requireYoutubeActorVerified() {
  const identity = await refreshYoutubeActorIdentity({ forceHeartbeat: true });
  if (identity.verified && !identity.blocked) {
    return { ok: true, identity };
  }
  return {
    ok: false,
    error: identity.code || "actor_not_verified",
    message: actorGuardMessage(identity),
    identity
  };
}

function actorGuardMessage(identity) {
  if (identity.code === "not_bound") return "Bind the local backend account before collecting.";
  if (identity.code === "login_required") return "Local backend login required.";
  if (identity.code === "backend_unavailable") return "Local backend is not available.";
  if (identity.code === "heartbeat_failed") return "Local account heartbeat failed.";
  return "Local account verification is required before collecting.";
}

async function bindYoutubeActorFromLogin() {
  await patchActorIdentity({ state: "checking", code: "binding", blocked: true, verified: false });
  try {
    const response = await fetch(`${YOUTUBE_IDENTITY_BASE_URL}/api/local/extension/actor-config`, {
      method: "GET",
      credentials: "include",
      cache: "no-store"
    });
    const body = await readJsonResponse(response);
    if (!response.ok) {
      if (response.status === 401) {
        await openYoutubeIdentityLogin();
        throw new Error("Local backend login required.");
      }
      throw new Error(body?.detail || body?.error || body?.raw || `HTTP ${response.status}`);
    }
    const config = normalizeYoutubeActorConfig(body);
    if (!config) throw new Error("Local backend did not return a valid plugin identity.");
    actorConfigCache = config;
    await chrome.storage.local.set({
      [ACTOR_CONFIG_KEY]: config,
      [LAST_HEARTBEAT_KEY]: null
    });
    const identity = await refreshYoutubeActorIdentity({ forceHeartbeat: true });
    const state = {
      ...(await getState()),
      actor_identity: identity,
      message: identity.verified ? "Ready." : actorGuardMessage(identity)
    };
    await setState(state);
    return { ok: identity.verified, state, identity };
  } catch (error) {
    const identity = buildYoutubeActorIdentity({
      config: await getYoutubeActorConfig(),
      heartbeat: null,
      code: String(errorText(error)).includes("login required") ? "login_required" : "bind_failed",
      detail: errorText(error),
      state: "error",
      blocked: true
    });
    const state = {
      ...(await getState()),
      actor_identity: identity,
      status: "error",
      message: errorText(error)
    };
    await setState(state);
    return { ok: false, error: errorText(error), state, identity };
  }
}

async function openYoutubeIdentityLogin() {
  const loginUrl = `${YOUTUBE_IDENTITY_BASE_URL}/login?next=/portal/`;
  await chrome.tabs.create({ url: loginUrl, active: true }).catch(() => undefined);
  const identity = await refreshYoutubeActorIdentity({ heartbeatIfStale: false });
  const state = {
    ...(await getState()),
    actor_identity: identity,
    message: "Local backend login required."
  };
  await setState(state);
  return { ok: true, state, login_url: loginUrl };
}

async function refreshYoutubeActorIdentity(options = {}) {
  const config = await getYoutubeActorConfig();
  if (!config) {
    return buildYoutubeActorIdentity({ config: null, heartbeat: null, code: "not_bound", state: "error", blocked: true });
  }

  let heartbeat = await getLastYoutubeHeartbeat();
  const forceHeartbeat = Boolean(options.forceHeartbeat);
  const heartbeatIfStale = options.heartbeatIfStale !== false;
  if (forceHeartbeat || (heartbeatIfStale && isYoutubeHeartbeatStale(heartbeat))) {
    heartbeat = await postYoutubeActorHeartbeat(forceHeartbeat ? "force_check" : "panel_refresh");
  }
  return buildYoutubeActorIdentity({ config, heartbeat });
}

async function postYoutubeActorHeartbeat(reason) {
  if (actorHeartbeatPromise) return actorHeartbeatPromise;
  actorHeartbeatPromise = (async () => {
    const config = await getYoutubeActorConfig();
    const actor = youtubeActorFromUser(config?.actor);
    const identity = await ensureYoutubeStableWorkerIdentity();
    const state = await getState().catch(() => ({}));
    const activeTab = await getActiveTab().catch(() => null);
    const payload = {
      event_type: "extension_heartbeat",
      extension_id: identity.extensionId,
      extension_version: chrome.runtime.getManifest().version,
      source: "youtube",
      status: state.status || "idle",
      running: state.status === "running",
      current_action: state.message || reason || "",
      current_handle: "",
      search_keyword: state.keyword || state.settings?.keyword || "",
      worker_id: identity.workerId,
      account_id: identity.accountId,
      actor_user_id: actor?.id || null,
      actor: actor || null,
      department_code: actor?.department_code || null,
      browser_profile: "chrome_default",
      current_url: activeTab?.url || null,
      page_type: classifyYoutubePage(activeTab?.url || ""),
      active_tab_title: activeTab?.title || null,
      timestamp: new Date().toISOString(),
      reason
    };
    attachYoutubeActorIdentity(payload, config);
    try {
      const response = await fetch(`${YOUTUBE_IDENTITY_BASE_URL}/api/local/extension/heartbeat`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const body = await readJsonResponse(response);
      const heartbeat = {
        ok: response.ok,
        status: response.status,
        detail: responseDetail(body, response.ok ? "" : `HTTP ${response.status}`),
        actor_user_id: payload.actor_user_id || null,
        at: new Date().toISOString()
      };
      await chrome.storage.local.set({ [LAST_HEARTBEAT_KEY]: heartbeat });
      return heartbeat;
    } catch (error) {
      const heartbeat = {
        ok: false,
        status: 0,
        detail: errorText(error),
        actor_user_id: payload.actor_user_id || null,
        at: new Date().toISOString()
      };
      await chrome.storage.local.set({ [LAST_HEARTBEAT_KEY]: heartbeat });
      return heartbeat;
    } finally {
      actorHeartbeatPromise = null;
    }
  })();
  return actorHeartbeatPromise;
}

async function patchActorIdentity(identity) {
  const state = await getState();
  await setState({ ...state, actor_identity: identity });
}

async function getYoutubeActorConfig() {
  if (actorConfigCache) return actorConfigCache;
  const stored = await chrome.storage.local.get([ACTOR_CONFIG_KEY]).catch(() => ({}));
  actorConfigCache = normalizeYoutubeActorConfig(stored[ACTOR_CONFIG_KEY]) || null;
  return actorConfigCache;
}

async function getLastYoutubeHeartbeat() {
  const stored = await chrome.storage.local.get([LAST_HEARTBEAT_KEY]).catch(() => ({}));
  return stored[LAST_HEARTBEAT_KEY] || null;
}

function isYoutubeHeartbeatStale(heartbeat) {
  if (!heartbeat?.at) return true;
  const time = Date.parse(heartbeat.at);
  if (!Number.isFinite(time)) return true;
  return Date.now() - time > HEARTBEAT_STALE_MS;
}

function normalizeYoutubeActorConfig(config) {
  if (!config || config.ok === false) return null;
  const actor = youtubeActorFromUser(config.actor);
  const actorToken = String(config.actor_token || "").trim();
  const downloadedAt = String(config.downloaded_at || config.actor_downloaded_at || "").trim();
  if (!actor || !actor.id || !actorToken || !downloadedAt) return null;
  return {
    ...config,
    ok: true,
    actor_user_id: actor.id,
    actor,
    actor_token: actorToken,
    downloaded_at: downloadedAt
  };
}

function youtubeActorFromUser(user) {
  if (!user) return null;
  const id = String(user.id || user.identity || "").trim();
  if (!id) return null;
  return {
    id,
    username: user.username || "",
    display_name: user.display_name || user.name || "",
    email: user.email || "",
    role: user.role || "",
    department_code: user.department_code || ""
  };
}

function buildYoutubeActorIdentity({ config, heartbeat, code, detail, state, blocked }) {
  const actor = youtubeActorFromUser(config?.actor);
  if (!actor || !config?.actor_token) {
    return {
      state: state || "error",
      code: code || "not_bound",
      blocked: blocked !== undefined ? Boolean(blocked) : true,
      verified: false,
      actor: null,
      downloaded_at: "",
      heartbeat_at: "",
      detail: detail || "",
      identity_base_url: YOUTUBE_IDENTITY_BASE_URL
    };
  }
  if (heartbeat?.ok) {
    return {
      state: "ok",
      code: "verified",
      blocked: false,
      verified: true,
      actor,
      downloaded_at: config.downloaded_at || "",
      heartbeat_at: heartbeat.at || "",
      detail: heartbeat.detail || "",
      identity_base_url: YOUTUBE_IDENTITY_BASE_URL
    };
  }
  if (heartbeat) {
    return {
      state: heartbeat.status === 0 ? "warn" : "error",
      code: heartbeat.status === 401 ? "login_required" : (heartbeat.status === 0 ? "backend_unavailable" : "heartbeat_failed"),
      blocked: true,
      verified: false,
      actor,
      downloaded_at: config.downloaded_at || "",
      heartbeat_at: heartbeat.at || "",
      detail: heartbeat.detail || "",
      heartbeat_status: heartbeat.status,
      identity_base_url: YOUTUBE_IDENTITY_BASE_URL
    };
  }
  return {
    state: state || "checking",
    code: code || "checking",
    blocked: true,
    verified: false,
    actor,
    downloaded_at: config.downloaded_at || "",
    heartbeat_at: "",
    detail: detail || "",
    identity_base_url: YOUTUBE_IDENTITY_BASE_URL
  };
}

async function ensureYoutubeStableWorkerIdentity() {
  if (!stableWorkerIdentityPromise) {
    stableWorkerIdentityPromise = (async () => {
      const extensionId = String(chrome.runtime?.id || "x9-youtube-extension");
      const prefix = `x9_youtube_${extensionId}_`;
      const stored = await chrome.storage.local.get([STABLE_WORKER_ID_KEY]).catch(() => ({}));
      let workerId = String(stored[STABLE_WORKER_ID_KEY] || "").trim();
      if (!workerId.startsWith(prefix)) {
        workerId = `${prefix}${createUuid()}`;
        await chrome.storage.local.set({ [STABLE_WORKER_ID_KEY]: workerId }).catch(() => undefined);
      }
      return { extensionId, workerId, accountId: workerId };
    })();
  }
  return stableWorkerIdentityPromise;
}

async function youtubeActorUploadContext() {
  const config = await getYoutubeActorConfig();
  const actor = youtubeActorFromUser(config?.actor);
  const identity = await ensureYoutubeStableWorkerIdentity();
  const context = {
    extension_id: identity.extensionId,
    extension_version: chrome.runtime.getManifest().version,
    worker_id: identity.workerId,
    account_id: identity.accountId,
    actor_user_id: actor?.id || "",
    actor: actor || null,
    actor_token: config?.actor_token || "",
    actor_downloaded_at: config?.downloaded_at || ""
  };
  return context;
}

function attachYoutubeActorToRow(row, actorContext) {
  return {
    ...(row || {}),
    extension_id: actorContext.extension_id || "",
    extension_version: actorContext.extension_version || "",
    worker_id: actorContext.worker_id || "",
    account_id: actorContext.account_id || "",
    actor_user_id: actorContext.actor_user_id || "",
    actor: actorContext.actor || null,
    actor_token: actorContext.actor_token || "",
    actor_downloaded_at: actorContext.actor_downloaded_at || ""
  };
}

function attachYoutubeActorToState(state, actorContext) {
  const rows = getStoredRows(state).map((row) => attachYoutubeActorToRow(row, actorContext));
  return {
    ...(state || {}),
    ...actorContext,
    rows,
    result: state?.result
      ? {
          ...state.result,
          rows
        }
      : state?.result
  };
}

function attachYoutubeActorIdentity(payload, config) {
  const actor = youtubeActorFromUser(config?.actor);
  if (actor?.id) {
    payload.actor_user_id = actor.id;
    payload.actor = actor;
  }
  if (config?.actor_token) {
    payload.actor_token = config.actor_token;
    payload.actor_downloaded_at = config.downloaded_at || "";
  }
  return payload;
}

function responseDetail(body, fallback) {
  const raw = body && (body.detail || body.error || body.message);
  if (typeof raw === "string") return raw;
  if (raw) {
    try {
      return JSON.stringify(raw);
    } catch {
      return String(raw);
    }
  }
  return fallback || "";
}

function classifyYoutubePage(url) {
  if (!url || !X9YoutubeUtils.isYoutubeUrl(url)) return "unknown";
  try {
    const parsed = new URL(url);
    if (/\/results\b/i.test(parsed.pathname)) return "search_results";
    if (/\/watch\b/i.test(parsed.pathname)) return "video_page";
    if (/\/shorts\//i.test(parsed.pathname)) return "shorts_page";
    if (/\/about\b/i.test(parsed.pathname)) return "channel_about";
    if (X9YoutubeUtils.normalizeChannelUrl(url)) return "channel_profile";
  } catch {
    return "unknown";
  }
  return "youtube";
}

function createUuid() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

async function loadHistoricalKnownEmails(knownEmails) {
  try {
    let offset = 0;
    let total = 0;
    do {
      const payload = await fetchYoutubeLeadsPage({ hasEmail: true, limit: 500, offset });
      const items = Array.isArray(payload.items) ? payload.items : [];
      total = Number(payload.total || items.length || 0);
      for (const item of items) {
        for (const email of mergeEmails(item.emails, item.email ? [item.email] : [])) knownEmails.add(email);
      }
      offset += items.length;
      if (!items.length) break;
    } while (offset < total);
    await patchIncrementalUpload((upload) => ({
      ...upload,
      status: "history_loaded",
      known_emails: knownEmails.size,
      history_loaded: true,
      last_error: ""
    }));
  } catch (error) {
    await patchIncrementalUpload((upload) => ({
      ...upload,
      status: "history_error",
      history_loaded: false,
      last_error: `History email load failed: ${errorText(error)}`
    }));
  }
}

async function fetchYoutubeLeadsPage({ hasEmail, limit, offset }) {
  const params = new URLSearchParams();
  params.set("limit", String(limit || 500));
  params.set("offset", String(offset || 0));
  if (hasEmail !== undefined) params.set("has_email", hasEmail ? "true" : "false");
  const endpoint = `${YOUTUBE_IMPORT_BASE_URL}/api/local/youtube/leads?${params.toString()}`;
  let response;
  try {
    response = await fetch(endpoint, { credentials: "include" });
  } catch (error) {
    throw new Error(`Local backend is not available: ${errorText(error)}`);
  }
  const payload = await readJsonResponse(response);
  if (!response.ok) {
    const detail = payload?.detail || payload?.error || payload?.raw || response.statusText;
    throw new Error(response.status === 401 ? "Local backend login required." : `Leads request failed (${response.status}): ${detail}`);
  }
  return payload;
}

async function uploadYoutubeRow(row, context) {
  const filename = buildIncrementalImportFilename(row, context.settings);
  const endpoint = `${YOUTUBE_IMPORT_BASE_URL}/api/local/youtube/import?filename=${encodeURIComponent(filename)}&dry_run=false`;
  const actorContext = await youtubeActorUploadContext();
  const uploadRow = attachYoutubeActorToRow(row, actorContext);
  const payload = {
    ...actorContext,
    result: {
      keyword: context.settings?.keyword || "",
      source_search_url: context.sourceSearchUrl || "",
      settings: context.settings || {},
      rows: [uploadRow]
    }
  };
  await patchIncrementalUpload((upload) => ({
    ...upload,
    status: "uploading",
    attempted: upload.attempted + 1,
    last_error: "",
    last_endpoint: endpoint
  }));

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    const result = await readJsonResponse(response);
    if (!response.ok) {
      const detail = result?.detail || result?.error || result?.raw || response.statusText;
      throw new Error(response.status === 401 ? "Local backend login required." : `Upload failed (${response.status}): ${detail}`);
    }
    await patchIncrementalUpload((upload) => ({
      ...upload,
      status: "uploaded",
      succeeded: upload.succeeded + 1,
      last_result: result,
      last_error: "",
      last_uploaded_at: new Date().toISOString()
    }));
    return { ok: true, result };
  } catch (error) {
    await patchIncrementalUpload((upload) => ({
      ...upload,
      status: "error",
      failed: upload.failed + 1,
      last_error: errorText(error)
    }));
    return { ok: false, error: errorText(error) };
  }
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

function normalizeIncrementalUpload(upload) {
  return {
    attempted: Number(upload?.attempted || 0),
    succeeded: Number(upload?.succeeded || 0),
    failed: Number(upload?.failed || 0),
    skipped_duplicates: Number(upload?.skipped_duplicates || 0),
    known_emails: Number(upload?.known_emails || 0),
    history_loaded: Boolean(upload?.history_loaded),
    status: upload?.status || "idle",
    last_error: upload?.last_error || "",
    last_duplicate_email: upload?.last_duplicate_email || "",
    last_result: upload?.last_result || null,
    last_endpoint: upload?.last_endpoint || "",
    last_uploaded_at: upload?.last_uploaded_at || ""
  };
}

async function patchIncrementalUpload(updater) {
  const state = await getState();
  const current = normalizeIncrementalUpload(state.incremental_upload);
  const nextUpload = typeof updater === "function" ? updater(current) : { ...current, ...(updater || {}) };
  const nextCounts = {
    ...(state.counts || {}),
    duplicate_emails_skipped: nextUpload.skipped_duplicates
  };
  const nextResult = state.result
    ? {
        ...state.result,
        counts: {
          ...(state.result.counts || {}),
          duplicate_emails_skipped: nextUpload.skipped_duplicates
        }
      }
    : state.result;
  await setState({
    ...state,
    incremental_upload: nextUpload,
    counts: nextCounts,
    result: nextResult
  });
  return nextUpload;
}

function getStoredRows(state) {
  const rows = Array.isArray(state?.rows) ? state.rows : state?.result?.rows;
  return Array.isArray(rows) ? rows.slice() : [];
}

function getStoredVideos(state) {
  const videos = Array.isArray(state?.videos) ? state.videos : state?.result?.videos;
  return Array.isArray(videos) ? videos.slice() : [];
}

function buildCollectedVideoKeySet(rows, videos) {
  const keys = new Set();
  for (const item of rows || []) addCollectedVideo(keys, item);
  for (const item of videos || []) addCollectedVideo(keys, item);
  return keys;
}

function buildCollectedCommenterKeySet(rows) {
  const keys = new Set();
  for (const row of rows || []) {
    if (row?.source_type !== "comment_author_channel") continue;
    const normalized = X9YoutubeUtils.normalizeChannelUrl(row.comment_author_channel_url || "");
    if (normalized) keys.add(normalized);
  }
  return keys;
}

function addCollectedVideo(keys, item) {
  for (const key of collectedVideoKeys(item)) keys.add(key);
}

function hasCollectedVideo(keys, item) {
  return collectedVideoKeys(item).some((key) => keys.has(key));
}

function collectedVideoKeys(item) {
  const keys = [];
  const urlCandidates = [
    item?.video_url,
    item?.checked_video_url,
    item?.video?.video_url
  ];
  for (const rawUrl of urlCandidates) {
    const normalized = X9YoutubeUtils.normalizeVideoUrl(rawUrl || "");
    if (normalized) {
      keys.push(`url:${normalized}`);
      const id = X9YoutubeUtils.extractVideoId(normalized);
      if (id) keys.push(`id:${id}`);
    }
  }
  const idCandidates = [
    item?.video_id,
    item?.video?.video_id
  ];
  for (const rawId of idCandidates) {
    const id = String(rawId || "").trim();
    if (id) keys.push(`id:${id}`);
  }
  return Array.from(new Set(keys));
}

function uniqueCommenterChannels(comments) {
  return X9YoutubeUtils.dedupeBy(comments || [], (comment) => comment.author_channel_url);
}

function buildManualReviewRows(rows) {
  return X9YoutubeReviewQueue.buildManualReviewRows(rows || []);
}

function makeCounts(videos, comments, profilePages, rows, manualReviewRows = buildManualReviewRows(rows)) {
  return {
    videos,
    comments,
    profile_pages: profilePages,
    rows: rows.length,
    manual_review: manualReviewRows.length,
    emails: rows.filter((row) => row.email).length,
    contacts: rows.filter((row) => row.email).length,
    duplicate_emails_skipped: 0
  };
}

function emptyProfile(channelUrl) {
  const homeUrl = X9YoutubeUtils.channelHomeUrl(channelUrl) || channelUrl || "";
  const aboutUrl = X9YoutubeUtils.channelAboutUrl(channelUrl) || channelUrl || "";
  return {
    page_kind: "channel_profile",
    page_url: aboutUrl,
    channel_url: X9YoutubeUtils.normalizeChannelUrl(channelUrl) || channelUrl || "",
    channel_name: "",
    channel_id: X9YoutubeUtils.extractChannelId(channelUrl),
    channel_handle: X9YoutubeUtils.extractChannelHandle(channelUrl),
    email: "",
    emails: [],
    contacts: [],
    external_links: [],
    profile_text: "",
    hidden_email_button_present: false,
    captcha_required: false,
    checked_profile_url: aboutUrl,
    checked_channel_home_url: homeUrl,
    checked_about_url: aboutUrl,
    checked_video_url: "",
    fallback_video_checked: false,
    profile_pages_checked: 0,
    collected_at: new Date().toISOString()
  };
}

function applyManualVerifiedProfile(state, profile, activeUrl, emails) {
  const rows = getStoredRows(state);
  const videos = getStoredVideos(state);
  const counts = state.counts || state.result?.counts || {};
  const profileKeys = profileMatchKeys(profile, activeUrl);
  let matched = false;
  const nextRows = rows.map((row) => {
    if (matched || !rowMatchesProfile(row, profileKeys)) return row;
    matched = true;
    return withManualVerifiedEmail(row, profile, activeUrl, emails);
  });
  if (!matched) {
    nextRows.unshift(newManualVerifiedRow(state, profile, activeUrl, emails));
  }

  const manualReviewRows = buildManualReviewRows(nextRows);
  const nextCounts = makeCounts(
    Number(counts.videos ?? videos.length ?? 0),
    Number(counts.comments || 0),
    Number(counts.profile_pages || 0),
    nextRows,
    manualReviewRows
  );
  const result = {
    ...(state.result || {}),
    keyword: state.keyword || state.settings?.keyword || state.result?.keyword || "",
    source_search_url: state.result?.source_search_url || "",
    videos,
    rows: nextRows,
    manual_review_rows: manualReviewRows,
    counts: nextCounts,
    collected_at: new Date().toISOString()
  };
  return {
    ...state,
    rows: nextRows,
    manual_review_rows: manualReviewRows,
    videos,
    counts: nextCounts,
    result,
    finished_at: new Date().toISOString()
  };
}

function findVerifiedProfileRow(state, profile, activeUrl, emails) {
  const keys = profileMatchKeys(profile, activeUrl);
  const targetEmail = emails[0] || "";
  return getStoredRows(state).find((row) => {
    if (targetEmail && !rowEmailValues(row).includes(targetEmail)) return false;
    return rowMatchesProfile(row, keys);
  }) || newManualVerifiedRow(state, profile, activeUrl, emails);
}

function hasPendingManualReviewMatch(state, profile, activeUrl) {
  const keys = profileMatchKeys(profile, activeUrl);
  if (buildManualReviewRows(getStoredRows(state)).some((row) => rowMatchesProfile(row, keys))) return true;
  const navigation = state.manual_review_navigation || {};
  const navigationKeys = new Set();
  [
    navigation.current_review_url,
    navigation.current_channel_url
  ].forEach((value) => addChannelKeys(navigationKeys, value));
  for (const key of navigationKeys) {
    if (keys.has(key)) return true;
  }
  return false;
}

function withManualVerifiedEmail(row, profile, activeUrl, emails) {
  const channelUrl = bestProfileChannelUrl(profile, activeUrl)
    || X9YoutubeUtils.normalizeChannelUrl(row.creator_channel_url || row.comment_author_channel_url || "")
    || "";
  const pageUrl = profile.page_url || activeUrl || row.checked_about_url || row.checked_profile_url || "";
  const sourceType = row.source_type || "creator_channel";
  return {
    ...row,
    source_type: sourceType,
    creator_channel_url: sourceType === "creator_channel" ? (row.creator_channel_url || channelUrl) : (row.creator_channel_url || ""),
    comment_author_channel_url: sourceType === "comment_author_channel" ? (row.comment_author_channel_url || channelUrl) : (row.comment_author_channel_url || ""),
    email: emails[0] || "",
    emails_json: JSON.stringify(emails),
    email_source: "manual_verified_about",
    evidence_url: pageUrl,
    manual_review_url: "",
    hidden_email_button_present: false,
    captcha_required: false,
    review_reason: "",
    checked_profile_url: pageUrl || row.checked_profile_url || "",
    checked_about_url: pageUrl || row.checked_about_url || "",
    profile_text: profile.profile_text || row.profile_text || "",
    needs_manual_review: false,
    collected_at: new Date().toISOString()
  };
}

function newManualVerifiedRow(state, profile, activeUrl, emails) {
  const channelUrl = bestProfileChannelUrl(profile, activeUrl) || activeUrl || "";
  const pageUrl = profile.page_url || activeUrl || X9YoutubeUtils.channelAboutUrl(channelUrl) || "";
  const settings = state.settings || {};
  return {
    source_type: "creator_channel",
    keyword: state.keyword || settings.keyword || state.result?.keyword || "",
    video_id: "",
    content_type: "video",
    video_title: "",
    video_url: "",
    creator_channel_url: channelUrl,
    comment_author_name: "",
    comment_author_channel_url: "",
    email: emails[0] || "",
    emails_json: JSON.stringify(emails),
    email_source: "manual_verified_about",
    evidence_url: pageUrl,
    manual_review_url: "",
    hidden_email_button_present: false,
    captcha_required: false,
    review_reason: "",
    checked_profile_url: pageUrl,
    checked_channel_home_url: X9YoutubeUtils.channelHomeUrl(channelUrl) || "",
    checked_about_url: pageUrl,
    checked_video_url: "",
    profile_text: profile.profile_text || "",
    video_detail_text: "",
    needs_manual_review: false,
    collected_at: new Date().toISOString()
  };
}

function profileMatchKeys(profile, activeUrl) {
  const values = [
    profile?.channel_url,
    profile?.page_url,
    activeUrl
  ];
  const keys = new Set();
  for (const value of values) addChannelKeys(keys, value);
  if (profile?.channel_handle) keys.add(`handle:${normalizeHandle(profile.channel_handle)}`);
  return keys;
}

function rowMatchesProfile(row, keys) {
  if (!keys?.size) return false;
  const rowKeys = new Set();
  [
    row.creator_channel_url,
    row.comment_author_channel_url,
    row.checked_profile_url,
    row.checked_channel_home_url,
    row.checked_about_url,
    row.manual_review_url,
    row.evidence_url
  ].forEach((value) => addChannelKeys(rowKeys, value));
  const handle = X9YoutubeUtils.extractChannelHandle(row.creator_channel_url || row.comment_author_channel_url || row.checked_about_url || "");
  if (handle) rowKeys.add(`handle:${normalizeHandle(handle)}`);
  for (const key of rowKeys) {
    if (keys.has(key)) return true;
  }
  return false;
}

function addChannelKeys(keys, value) {
  const normalized = X9YoutubeUtils.normalizeChannelUrl(value || "");
  if (normalized) {
    keys.add(`url:${normalized}`);
    const handle = X9YoutubeUtils.extractChannelHandle(normalized);
    if (handle) keys.add(`handle:${normalizeHandle(handle)}`);
    const id = X9YoutubeUtils.extractChannelId(normalized);
    if (id) keys.add(`id:${id}`);
  }
  const handle = X9YoutubeUtils.extractChannelHandle(value || "");
  if (handle) keys.add(`handle:${normalizeHandle(handle)}`);
}

function bestProfileChannelUrl(profile, activeUrl) {
  return X9YoutubeUtils.normalizeChannelUrl(profile?.channel_url || "")
    || X9YoutubeUtils.normalizeChannelUrl(profile?.page_url || "")
    || X9YoutubeUtils.normalizeChannelUrl(activeUrl || "")
    || "";
}

function normalizeHandle(value) {
  return String(value || "").trim().replace(/^@+/, "@").toLowerCase();
}

async function uploadYoutubeImport(state) {
  const filename = buildImportFilename(state);
  const endpoint = `${YOUTUBE_IMPORT_BASE_URL}/api/local/youtube/import?filename=${encodeURIComponent(filename)}&dry_run=false`;
  const actorContext = await youtubeActorUploadContext();
  const uploadState = attachYoutubeActorToState(state, actorContext);
  const uploading = {
    ok: null,
    status: "uploading",
    endpoint,
    filename,
    started_at: new Date().toISOString(),
    finished_at: ""
  };
  await setState({
    ...state,
    ingest_upload: uploading,
    message: "Collection complete. Uploading to local YouTube database..."
  });

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(uploadState)
    });
    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { raw: text };
      }
    }
    if (!response.ok) {
      const detail = payload?.detail || payload?.error || payload?.raw || response.statusText;
      throw new Error(response.status === 401 ? "Local backend login required." : `Upload failed (${response.status}): ${detail}`);
    }
    const next = {
      ...(await getState()),
      ingest_upload: {
        ...uploading,
        ok: true,
        status: "uploaded",
        result: payload,
        finished_at: new Date().toISOString()
      },
      message: "Collection complete. Uploaded to local YouTube database."
    };
    await setState(next);
    return next;
  } catch (error) {
    const next = {
      ...(await getState()),
      ingest_upload: {
        ...uploading,
        ok: false,
        status: "error",
        error: errorText(error),
        finished_at: new Date().toISOString()
      },
      message: `Collection complete. Upload failed: ${errorText(error)}`
    };
    await setState(next);
    return next;
  }
}

async function openNextManualReview() {
  const actorGuard = await requireYoutubeActorVerified();
  if (!actorGuard.ok) {
    const state = {
      ...(await getState()),
      status: "error",
      message: actorGuard.message,
      actor_identity: actorGuard.identity
    };
    await setState(state);
    return { ok: false, error: actorGuard.error, state };
  }

  const previousState = await getState();
  await setState({
    ...previousState,
    actor_identity: actorGuard.identity,
    status: "running",
    message: "Loading manual review queue..."
  });

  try {
    const activeTab = await getActiveTab();
    const payload = await fetchManualReviewLeads();
    const reviewItems = (Array.isArray(payload.items) ? payload.items : [])
      .filter((item) => item?.needs_manual_review)
      .map((item) => ({ ...item, review_url: manualReviewAboutUrl(item) }))
      .filter((item) => item.review_url);

    if (!reviewItems.length) {
      const state = {
        ...(await getState()),
        status: "done",
        message: "No manual review leads found.",
        manual_review_navigation: {
          total: Number(payload.total || 0),
          opened_lead_ids: [],
          current_lead_id: "",
          current_review_url: "",
          updated_at: new Date().toISOString()
        }
      };
      await setState(state);
      return { ok: true, state };
    }

    const currentState = await getState();
    const navigation = currentState.manual_review_navigation || {};
    const validIds = new Set(reviewItems.map((item) => item.id).filter(Boolean));
    const opened = (Array.isArray(navigation.opened_lead_ids) ? navigation.opened_lead_ids : [])
      .filter((id) => validIds.has(id));
    let openedSet = new Set(opened);
    let nextLead = reviewItems.find((item) => !openedSet.has(item.id));
    let nextOpened = opened.slice();
    if (!nextLead) {
      nextLead = reviewItems[0];
      nextOpened = [];
      openedSet = new Set();
    }
    if (nextLead.id && !openedSet.has(nextLead.id)) nextOpened.push(nextLead.id);

    const tab = await openReviewUrlInActiveContext(activeTab, nextLead.review_url);
    const state = {
      ...(await getState()),
      status: "done",
      message: "Opened next manual review About page.",
      manual_review_navigation: {
        total: Number(payload.total || reviewItems.length || 0),
        opened_lead_ids: nextOpened,
        current_lead_id: nextLead.id || "",
        current_review_url: nextLead.review_url,
        current_channel_url: nextLead.channel_url || "",
        current_display_name: nextLead.display_name || nextLead.channel_handle || "",
        current_tab_id: tab?.id || null,
        updated_at: new Date().toISOString()
      }
    };
    await setState(state);
    return { ok: true, state };
  } catch (error) {
    const state = {
      ...(await getState()),
      status: "error",
      message: errorText(error)
    };
    await setState(state);
    return { ok: false, error: errorText(error), state };
  }
}

async function fetchManualReviewLeads() {
  const endpoint = `${YOUTUBE_IMPORT_BASE_URL}/api/local/youtube/manual-review?limit=500`;
  let response;
  try {
    response = await fetch(endpoint, { credentials: "include" });
  } catch (error) {
    throw new Error(`Local backend is not available: ${errorText(error)}`);
  }
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text };
    }
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.error || payload?.raw || response.statusText;
    throw new Error(response.status === 401 ? "Local backend login required." : `Manual review request failed (${response.status}): ${detail}`);
  }
  return payload;
}

function manualReviewAboutUrl(lead) {
  const channelUrl = X9YoutubeUtils.normalizeChannelUrl(lead?.channel_url || "");
  const channelAboutUrl = X9YoutubeUtils.channelAboutUrl(channelUrl || lead?.channel_url || "");
  const reviewUrl = normalizeManualReviewUrl(lead?.manual_review_url || "");
  if (reviewUrl && X9YoutubeUtils.normalizeChannelUrl(reviewUrl)) return reviewUrl;
  return channelAboutUrl || reviewUrl;
}

function normalizeManualReviewUrl(value) {
  try {
    const parsed = new URL(value || "", "https://www.youtube.com");
    if (!X9YoutubeUtils.isYoutubeUrl(parsed.toString())) return "";
    const channelUrl = X9YoutubeUtils.normalizeChannelUrl(parsed.toString());
    if (channelUrl) return X9YoutubeUtils.channelAboutUrl(channelUrl);
    return parsed.toString();
  } catch {
    return "";
  }
}

async function openReviewUrlInActiveContext(activeTab, url) {
  if (activeTab?.id && X9YoutubeUtils.isYoutubeUrl(activeTab.url || "")) {
    const updated = await chrome.tabs.update(activeTab.id, { url, active: true });
    await waitForTabComplete(activeTab.id, 12000);
    return updated || activeTab;
  }
  const createOptions = { url, active: true };
  if (activeTab?.windowId) createOptions.windowId = activeTab.windowId;
  const tab = await chrome.tabs.create(createOptions);
  await waitForTabComplete(tab.id, 12000);
  return tab;
}

async function collectCurrentPageEmail() {
  const actorGuard = await requireYoutubeActorVerified();
  if (!actorGuard.ok) {
    const state = {
      ...(await getState()),
      status: "error",
      message: actorGuard.message,
      actor_identity: actorGuard.identity
    };
    await setState(state);
    return { ok: false, error: actorGuard.error, state };
  }

  const activeTab = await getActiveTab();
  const previousState = await getState();
  if (!activeTab?.id || !X9YoutubeUtils.isYoutubeUrl(activeTab.url || "")) {
    const state = {
      ...previousState,
      status: "error",
      message: "Open a YouTube About dialog with a visible email first."
    };
    await setState(state);
    return { ok: false, error: "active_tab_is_not_youtube", state };
  }

  await setState({
    ...previousState,
    actor_identity: actorGuard.identity,
    status: "running",
    message: "Collecting visible email from current About dialog..."
  });

  try {
    await ensureContentScript(activeTab.id);
    const response = await sendTabMessage(activeTab.id, {
      type: MSG.CONTENT_COLLECT_PROFILE,
      settings: {
        ...(previousState.settings || {}),
        openAboutDialog: false
      }
    });
    if (!response?.ok) throw new Error(response?.error || "current_profile_collect_failed");

    const profile = response.result || {};
    const emails = mergeEmails(profile.emails, profile.email ? [profile.email] : []);
    if (!emails.length) {
      const state = {
        ...(await getState()),
        status: "error",
        message: "No visible email found on current About dialog."
      };
      await setState(state);
      return { ok: false, error: "no_visible_email_found", state };
    }

    const stateBeforeVerification = await getState();
    const matchesManualReview = hasPendingManualReviewMatch(stateBeforeVerification, profile, activeTab.url || "");
    const verifiedState = applyManualVerifiedProfile(stateBeforeVerification, profile, activeTab.url || "", emails);
    const knownEmails = buildKnownEmailSet(getStoredRows(stateBeforeVerification));
    await loadHistoricalKnownEmails(knownEmails);
    const duplicateEmail = emails.find((email) => knownEmails.has(email)) || "";
    if (duplicateEmail && !matchesManualReview) {
      await patchIncrementalUpload((upload) => ({
        ...upload,
        status: "skipped_duplicate",
        skipped_duplicates: upload.skipped_duplicates + 1,
        last_duplicate_email: duplicateEmail,
        last_error: ""
      }));
      const state = {
        ...(await getState()),
        status: "done",
        message: "Email already exists. Skipped duplicate import."
      };
      await setState(state);
      return { ok: true, state };
    }

    await setState({
      ...stateBeforeVerification,
      status: "running",
      message: "Collected current page email. Uploading to local YouTube database..."
    });
    const verifiedRow = findVerifiedProfileRow(verifiedState, profile, activeTab.url || "", emails);
    const uploadResult = await uploadYoutubeRow(verifiedRow, {
      rows: getStoredRows(verifiedState),
      videosOut: getStoredVideos(verifiedState),
      knownEmails,
      settings: verifiedState.settings || {},
      sourceSearchUrl: verifiedState.result?.source_search_url || "",
      buildPatch: () => ({
        rows: getStoredRows(verifiedState),
        manual_review_rows: buildManualReviewRows(getStoredRows(verifiedState)),
        videos: getStoredVideos(verifiedState),
        counts: verifiedState.counts || {}
      })
    });
    if (!uploadResult.ok) {
      const current = await getState();
      const rollbackState = {
        ...stateBeforeVerification,
        status: "error",
        incremental_upload: current.incremental_upload,
        message: `Current page email upload failed: ${uploadResult.error || "upload_failed"}`
      };
      await setState(rollbackState);
      return { ok: false, error: uploadResult.error || "upload_failed", state: rollbackState };
    }
    rememberRowEmails(verifiedRow, knownEmails);
    const finalState = {
      ...(await getState()),
      ...verifiedState,
      incremental_upload: (await getState()).incremental_upload,
      status: "done",
      message: "Current page email collected and uploaded."
    };
    await setState(finalState);
    return { ok: true, state: finalState };
  } catch (error) {
    const state = {
      ...(await getState()),
      status: "error",
      message: errorText(error)
    };
    await setState(state);
    return { ok: false, error: errorText(error), state };
  }
}

function buildImportFilename(state) {
  const keyword = safeFilenameSegment(state?.keyword || state?.settings?.keyword || "youtube_search");
  const runId = safeFilenameSegment(state?.run_id || String(Date.now()));
  return `x9-youtube-${keyword}-${runId}.json`;
}

function buildIncrementalImportFilename(row, settings = {}) {
  const keyword = safeFilenameSegment(settings.keyword || row?.keyword || "youtube_search");
  const source = safeFilenameSegment(row?.source_type || "row");
  const channel = safeFilenameSegment(row?.creator_channel_url || row?.comment_author_channel_url || row?.email || "channel");
  return `x9-youtube-row-${keyword}-${source}-${channel}-${Date.now()}.json`;
}

function safeFilenameSegment(value) {
  return String(value || "")
    .trim()
    .replace(/[^\w.-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "youtube";
}

async function stopActiveRun() {
  stopRequested = true;
  const state = await getState();
  const tabId = state.active_tab_id || (await getActiveTab())?.id;
  if (tabId) {
    await sendTabMessage(tabId, { type: MSG.CONTENT_STOP }).catch(() => undefined);
  }
  if (state.worker_tab_id && state.worker_tab_id !== tabId) {
    await closeWorkerTab(state.worker_tab_id, tabId).catch(() => undefined);
  }
  await activateSearchTab(tabId);
  const next = {
    ...state,
    status: state.status === "running" ? "stopping" : state.status,
    message: "Stop requested.",
    worker_tab_id: null
  };
  await setState(next);
  return { ok: true, state: next };
}

function createWorkerSession(openerTab) {
  return {
    openerTab,
    tab: null
  };
}

async function openWorkerTab(session, url) {
  if (!session) throw new Error("missing_worker_session");

  const createOptions = {
    url,
    active: true
  };
  if (session.openerTab?.windowId) createOptions.windowId = session.openerTab.windowId;
  if (session.openerTab?.id) createOptions.openerTabId = session.openerTab.id;
  const tab = await chrome.tabs.create(createOptions);
  session.tab = tab;
  return tab;
}

async function navigateWorkerTab(session, url) {
  if (!session) throw new Error("missing_worker_session");
  const existing = session.tab?.id ? await chrome.tabs.get(session.tab.id).catch(() => null) : null;
  if (existing?.id) {
    const updated = await chrome.tabs.update(existing.id, { url, active: true });
    session.tab = updated || existing;
    return session.tab;
  }
  return openWorkerTab(session, url);
}

async function openCollectionTab(workerSession, url) {
  if (workerSession) {
    return {
      tab: await navigateWorkerTab(workerSession, url),
      shouldClose: false
    };
  }
  return {
    tab: await chrome.tabs.create({ url, active: false }),
    shouldClose: true
  };
}

async function navigateCollectionTab(collectionTab, workerSession, url) {
  if (workerSession) {
    collectionTab.tab = await navigateWorkerTab(workerSession, url);
    return collectionTab.tab;
  }
  const updated = await chrome.tabs.update(collectionTab.tab.id, { url, active: false });
  collectionTab.tab = updated || collectionTab.tab;
  return collectionTab.tab;
}

async function closeWorkerSession(session, searchTabId) {
  await closeWorkerTab(session?.tab?.id, searchTabId);
  if (session) session.tab = null;
}

async function closeWorkerTab(tabId, searchTabId) {
  if (!tabId || tabId === searchTabId) return;
  await sendTabMessage(tabId, { type: MSG.CONTENT_STOP }).catch(() => undefined);
  await chrome.tabs.remove(tabId).catch(() => undefined);
}

async function activateSearchTab(tabId) {
  if (!tabId) return;
  await chrome.tabs.update(tabId, { active: true }).catch(() => undefined);
}

async function ensureContentScript(tabId) {
  try {
    const pong = await sendTabMessage(tabId, { type: MSG.CONTENT_PING });
    if (pong?.ok) return;
  } catch {
    // Content script may not be present on pages opened before installing.
  }
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["contact_detector.js", "youtube_utils.js", "youtube_content.js"]
  });
  await sleep(150);
}

async function waitForTabComplete(tabId, timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (tab?.status === "complete") {
      await sleep(500);
      return tab;
    }
    await sleep(250);
  }
  return chrome.tabs.get(tabId).catch(() => null);
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs?.[0] || null;
}

function sendTabMessage(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(err.message || String(err)));
      else resolve(response);
    });
  });
}

async function addLog(type, message) {
  const state = await getState();
  const logs = Array.isArray(state.logs) ? state.logs.slice(-200) : [];
  logs.push({ type, message, at: new Date().toISOString() });
  await patchState({ logs });
}

async function patchState(patch) {
  const current = await getState();
  const next = { ...current, ...patch };
  if (patch.counts) {
    next.counts = {
      ...patch.counts,
      duplicate_emails_skipped: normalizeIncrementalUpload(next.incremental_upload).skipped_duplicates
    };
  }
  if (patch.result?.counts) {
    next.result = {
      ...patch.result,
      counts: {
        ...patch.result.counts,
        duplicate_emails_skipped: normalizeIncrementalUpload(next.incremental_upload).skipped_duplicates
      }
    };
  }
  await setState(next);
}

async function ensureInitialState() {
  const stored = await chrome.storage.local.get([STORE_KEY]).catch(() => ({}));
  if (!stored[STORE_KEY]) await setState(defaultState());
}

async function getState() {
  const stored = await chrome.storage.local.get([STORE_KEY]).catch(() => ({}));
  return stored[STORE_KEY] || defaultState();
}

function setState(state) {
  const next = { ...(state || {}) };
  if (next.counts) {
    next.counts = withIncrementalUploadCounts(next.counts, next.incremental_upload);
  }
  if (next.result?.counts) {
    next.result = {
      ...next.result,
      counts: withIncrementalUploadCounts(next.result.counts, next.incremental_upload)
    };
  }
  return chrome.storage.local.set({ [STORE_KEY]: next });
}

function withIncrementalUploadCounts(counts, upload) {
  if (!counts) return counts;
  return {
    ...counts,
    duplicate_emails_skipped: normalizeIncrementalUpload(upload).skipped_duplicates
  };
}

function defaultState() {
  return {
    mode: "manual_search_results",
    status: "idle",
    message: "Open a YouTube search results page, then start.",
    keyword: "",
    settings: normalizeSettings({}),
    result: null,
    rows: [],
    manual_review_rows: [],
    videos: [],
    counts: {},
    logs: [],
    ingest_upload: null,
    incremental_upload: normalizeIncrementalUpload(null),
    actor_identity: {
      state: "checking",
      code: "checking",
      blocked: true,
      verified: false
    },
    manual_review_navigation: {
      total: 0,
      opened_lead_ids: [],
      current_lead_id: "",
      current_review_url: "",
      current_channel_url: "",
      current_display_name: "",
      current_tab_id: null,
      updated_at: ""
    },
    active_tab_id: null,
    worker_tab_id: null,
    run_id: "",
    started_at: "",
    finished_at: ""
  };
}

function normalizeSettings(settings) {
  const collectCommenters = parseBoolean(settings.collectCommenters, false);
  const collectCreators = collectCommenters ? true : parseBoolean(settings.collectCreators, true);
  return {
    keyword: String(settings.keyword || "").trim(),
    collectCreators,
    collectCommenters,
    maxVideos: clampNumber(settings.maxVideos, 1, 100, 5),
    maxCommentsPerVideo: clampNumber(settings.maxCommentsPerVideo ?? settings.maxComments, 1, 200, 50),
    maxCommenterProfilesPerVideo: clampNumber(settings.maxCommenterProfilesPerVideo ?? settings.maxCommenterProfiles, 0, 200, 50),
    searchScrollRounds: clampNumber(settings.searchScrollRounds, 0, 30, 10),
    scrollRounds: clampNumber(settings.scrollRounds, 0, 30, 8),
    waitMs: clampNumber(settings.waitMs, 250, 3000, 900),
    profileSettleMs: clampNumber(settings.profileSettleMs, 500, 6000, 1800),
    betweenProfilesMs: clampNumber(settings.betweenProfilesMs, 0, 5000, 350)
  };
}

function parseBoolean(value, fallback) {
  if (value === true || value === "true" || value === 1 || value === "1") return true;
  if (value === false || value === "false" || value === 0 || value === "0") return false;
  return fallback;
}

function isYoutubeSearchResultsUrl(url) {
  try {
    const parsed = new URL(url);
    return X9YoutubeUtils.isYoutubeUrl(url) && /\/results\b/i.test(parsed.pathname);
  } catch {
    return false;
  }
}

function isSameSearchScope(previousUrl, currentUrl, previousKeyword, currentKeyword) {
  const previous = searchScopeKey(previousUrl, previousKeyword);
  const current = searchScopeKey(currentUrl, currentKeyword);
  return Boolean(previous && current && previous === current);
}

function searchScopeKey(url, keyword) {
  const fallbackKeyword = String(keyword || "").trim().toLowerCase();
  try {
    const parsed = new URL(url || "");
    const query = String(parsed.searchParams.get("search_query") || fallbackKeyword).trim().toLowerCase();
    const path = parsed.pathname.replace(/\/+$/, "") || "/";
    return `${parsed.hostname.toLowerCase()}${path}?search_query=${query}`;
  } catch {
    return fallbackKeyword ? `keyword:${fallbackKeyword}` : "";
  }
}

function extractSearchKeyword(url) {
  try {
    return new URL(url).searchParams.get("search_query") || "";
  } catch {
    return "";
  }
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
