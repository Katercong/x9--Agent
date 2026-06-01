(function () {
  const SETTINGS_KEY = "x9_xhs_settings";
  const DEFAULT_SETTINGS = {
    maxNotes: 10,
    profileLimit: 20
  };

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    if (!el("xhsPanel")) return;
    bind();
    await loadSettings();
    await refresh();
    setInterval(refresh, 1200);
  }

  function bind() {
    el("xhsStartBtn")?.addEventListener("click", onStart);
    el("xhsStopBtn")?.addEventListener("click", () => runtimeSend({ type: "XHS_STOP" }).then(refresh));
    el("xhsResetBtn")?.addEventListener("click", async () => {
      await runtimeSend({ type: "XHS_RESET" });
      await chrome.storage.local.set({ [SETTINGS_KEY]: DEFAULT_SETTINGS });
      await loadSettings();
      setStatus("idle", "空闲");
      setStep("");
      setText("xhsPhase", "");
      setError("");
      for (const id of ["xhsNotesCount", "xhsCommentsCount", "xhsRepliesCount", "xhsUsersCount", "xhsProfilesCount"]) {
        setText(id, 0);
      }
    });

    for (const id of ["xhsProfileLimitInput", "xhsMaxNotesInput"]) {
      el(id)?.addEventListener("change", saveSettings);
      el(id)?.addEventListener("input", saveSettings);
    }
  }

  async function onStart() {
    const settings = readSettings();
    await saveSettings();
    setError("");
    setStatus("running", "启动中");
    setStep("notes");
    setText("xhsPhase", "启动中");
    const resp = await runtimeSend({ type: "XHS_START", settings });
    if (!resp || !resp.ok) {
      setStatus("error", "失败");
      setStep("");
      setError((resp && (resp.error || resp.message)) || "启动失败，请确认当前标签页是小红书搜索结果页。");
    }
    await refresh();
  }

  async function loadSettings() {
    const saved = await chrome.storage.local.get(SETTINGS_KEY);
    const settings = Object.assign({}, DEFAULT_SETTINGS, saved[SETTINGS_KEY] || {});
    el("xhsProfileLimitInput").value = settings.profileLimit || DEFAULT_SETTINGS.profileLimit;
    el("xhsMaxNotesInput").value = settings.maxNotes || DEFAULT_SETTINGS.maxNotes;
  }

  async function saveSettings() {
    await chrome.storage.local.set({ [SETTINGS_KEY]: readSettings() });
  }

  function readSettings() {
    return {
      profileLimit: clamp(el("xhsProfileLimitInput").value, 1, 300, DEFAULT_SETTINGS.profileLimit),
      maxNotes: clamp(el("xhsMaxNotesInput").value, 1, 200, DEFAULT_SETTINGS.maxNotes)
    };
  }

  async function refresh() {
    const resp = await runtimeSend({ type: "XHS_GET_STATE" });
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

    setText("xhsNotesCount", counts.notes || 0);
    setText("xhsCommentsCount", counts.comments || 0);
    setText("xhsRepliesCount", counts.replies || 0);
    setText("xhsUsersCount", counts.users || 0);
    setText("xhsProfilesCount", counts.profiles || 0);
    setStatus(status, statusLabel(status));
    setStep(stepFromState(state));
    setText("xhsPhase", phaseText);
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
    const pill = el("xhsStatusPill");
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
    const node = el("xhsError");
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("error", Boolean(text));
  }

  function setStep(step) {
    const map = {
      notes: "xhsStepNotes",
      comments: "xhsStepComments",
      profiles: "xhsStepProfiles",
      upload: "xhsStepUpload"
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
