(function () {
  const SETTINGS_KEY = "x9_douyin_settings";
  const DEFAULT_SETTINGS = {
    limitMode: "profiles",
    maxPosts: 10,
    profileLimit: 20
  };

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    if (!el("douyinPanel")) return;
    bind();
    await loadSettings();
    await refresh();
    setInterval(refresh, 1200);
  }

  function bind() {
    el("douyinStartBtn")?.addEventListener("click", onStart);
    el("douyinStopBtn")?.addEventListener("click", () => runtimeSend({ type: "DOUYIN_STOP" }).then(refresh));
    el("douyinResetBtn")?.addEventListener("click", async () => {
      await runtimeSend({ type: "DOUYIN_RESET" });
      await chrome.storage.local.set({ [SETTINGS_KEY]: DEFAULT_SETTINGS });
      await loadSettings();
      setStatus("idle", "空闲");
      setStep("");
      setText("douyinPhase", "");
      setError("");
      for (const id of ["douyinPostsCount", "douyinCommentsCount", "douyinRepliesCount", "douyinUsersCount", "douyinProfilesCount"]) {
        setText(id, 0);
      }
    });

    for (const id of ["douyinLimitModeProfiles", "douyinLimitModeVideos"]) {
      el(id)?.addEventListener("change", () => {
        updateLimitModeUi(readLimitMode());
        saveSettings();
      });
    }

    for (const id of ["douyinProfileLimitInput", "douyinMaxPostsInput"]) {
      el(id)?.addEventListener("focus", () => {
        setLimitMode(id === "douyinProfileLimitInput" ? "profiles" : "videos");
        saveSettings();
      });
      el(id)?.addEventListener("change", () => {
        setLimitMode(id === "douyinProfileLimitInput" ? "profiles" : "videos");
        saveSettings();
      });
      el(id)?.addEventListener("input", () => {
        setLimitMode(id === "douyinProfileLimitInput" ? "profiles" : "videos");
        saveSettings();
      });
    }
  }

  async function onStart() {
    const settings = readSettings();
    await saveSettings();
    setError("");
    setStatus("running", "启动中");
    setStep("posts");
    setText("douyinPhase", "启动中");
    const resp = await runtimeSend({ type: "DOUYIN_START", settings });
    if (!resp || !resp.ok) {
      setStatus("error", "失败");
      setStep("");
      setError((resp && (resp.error || resp.message)) || "启动失败，请确认当前标签页是抖音搜索结果页。");
    }
    await refresh();
  }

  async function loadSettings() {
    const saved = await chrome.storage.local.get(SETTINGS_KEY);
    const settings = Object.assign({}, DEFAULT_SETTINGS, saved[SETTINGS_KEY] || {});
    setLimitMode(normalizeLimitMode(settings.limitMode));
    el("douyinProfileLimitInput").value = settings.profileLimit || DEFAULT_SETTINGS.profileLimit;
    el("douyinMaxPostsInput").value = settings.maxPosts || DEFAULT_SETTINGS.maxPosts;
    updateLimitModeUi(readLimitMode());
  }

  async function saveSettings() {
    await chrome.storage.local.set({ [SETTINGS_KEY]: readSettings() });
  }

  function readSettings() {
    return {
      limitMode: readLimitMode(),
      profileLimit: clamp(el("douyinProfileLimitInput").value, 1, 300, DEFAULT_SETTINGS.profileLimit),
      maxPosts: clamp(el("douyinMaxPostsInput").value, 1, 200, DEFAULT_SETTINGS.maxPosts)
    };
  }

  function readLimitMode() {
    return normalizeLimitMode(document.querySelector('input[name="douyinLimitMode"]:checked')?.value);
  }

  function setLimitMode(mode) {
    const value = normalizeLimitMode(mode);
    const target = value === "videos" ? el("douyinLimitModeVideos") : el("douyinLimitModeProfiles");
    if (target) target.checked = true;
    updateLimitModeUi(value);
  }

  function updateLimitModeUi(mode) {
    const value = normalizeLimitMode(mode);
    el("douyinProfileLimitInput")?.closest(".xhs-field")?.classList.toggle("is-limit-active", value === "profiles");
    el("douyinMaxPostsInput")?.closest(".xhs-field")?.classList.toggle("is-limit-active", value === "videos");
  }

  function normalizeLimitMode(mode) {
    return mode === "videos" ? "videos" : "profiles";
  }

  async function refresh() {
    const resp = await runtimeSend({ type: "DOUYIN_GET_STATE" });
    if (!resp || !resp.ok) {
      setStatus("idle", "后台未就绪");
      setStep("");
      setError((resp && resp.error) || "插件后台未响应，请在 chrome://extensions 重新加载插件。");
      return;
    }

    const state = resp.state || {};
    const counts = state.counts || {};
    const upload = state.ingestUpload || null;
    const uploadFailed = Boolean(upload && upload.ok === false);
    const status = uploadFailed ? "error" : (state.status || "idle");
    const phaseText = buildPhaseText(state, upload);

    setText("douyinPostsCount", counts.posts || 0);
    setText("douyinCommentsCount", counts.comments || 0);
    setText("douyinRepliesCount", counts.replies || 0);
    setText("douyinUsersCount", counts.users || 0);
    setText("douyinProfilesCount", counts.profiles || 0);
    setStatus(status, statusLabel(status));
    setStep(stepFromState(state));
    setText("douyinPhase", phaseText);
    setError(status === "error" ? phaseText : "");
  }

  function buildPhaseText(state, upload) {
    if (upload && upload.ok === true) return "上传成功";
    if (upload && upload.ok === false) return `上传失败：${upload.error || "unknown_error"}`;
    if (state.phase === "upload") return "上传中";
    if (state.status === "done") return "采集完成";
    if (state.status === "paused") return "已停止";
    if (state.status === "error") return state.message || "采集失败";
    if (state.status === "running") return state.message || "采集中";
    return "";
  }

  function runtimeSend(message) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError) return resolve({ ok: false, error: chrome.runtime.lastError.message });
          resolve(response || { ok: true });
        });
      } catch (error) {
        resolve({ ok: false, error: String(error && error.message || error) });
      }
    });
  }

  function setStatus(state, text) {
    const pill = el("douyinStatusPill");
    if (!pill) return;
    pill.dataset.state = state;
    pill.textContent = text || state;
  }

  function statusLabel(status) {
    if (status === "running") return "运行中";
    if (status === "done") return "完成";
    if (status === "paused") return "已停止";
    if (status === "error") return "失败";
    return "空闲";
  }

  function setError(text) {
    const node = el("douyinError");
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("error", Boolean(text));
  }

  function setStep(step) {
    const map = {
      posts: "douyinStepPosts",
      comments: "douyinStepComments",
      profiles: "douyinStepProfiles",
      upload: "douyinStepUpload"
    };
    for (const id of Object.values(map)) el(id)?.classList.remove("active");
    el(map[step])?.classList.add("active");
  }

  function stepFromState(state) {
    if (state.phase === "upload" || state.status === "done" || state.ingestUpload) return "upload";
    if (state.status === "running") return state.phase || "";
    return "";
  }

  function setText(id, value) {
    const node = el(id);
    if (node) node.textContent = String(value ?? "");
  }

  function clamp(value, min, max, fallback) {
    const n = Number.parseInt(value, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function el(id) {
    return document.getElementById(id);
  }
})();
