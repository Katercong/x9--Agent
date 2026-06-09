(function () {
  const KEY = "x9YoutubeLang";
  const DEFAULT_LANG = "zh";
  const MESSAGES = {
    "Ready.": {
      zh: "\u51c6\u5907\u5c31\u7eea\u3002",
      en: "Ready."
    },
    "Starting from current search page...": {
      zh: "\u6b63\u5728\u4ece\u5f53\u524d\u641c\u7d22\u7ed3\u679c\u9875\u5f00\u59cb\u91c7\u96c6\u535a\u4e3b\u548c\u8bc4\u8bba\u7528\u6237\u90ae\u7bb1...",
      en: "Starting creator and commenter email run from current search page..."
    },
    "Continuing from previous results...": {
      zh: "\u6b63\u5728\u4ece\u4e0a\u6b21\u7ed3\u679c\u7ee7\u7eed\u91c7\u96c6...",
      en: "Continuing from previous results..."
    },
    "Opening next manual review About page...": {
      zh: "\u6b63\u5728\u6253\u5f00\u4e0b\u4e00\u4e2a\u4eba\u5de5\u5ba1\u6838 About \u9875...",
      en: "Opening next manual review About page..."
    },
    "Open next manual review failed.": {
      zh: "\u6253\u5f00\u4e0b\u4e00\u4e2a\u4eba\u5de5\u5ba1\u6838\u5931\u8d25\u3002",
      en: "Open next manual review failed."
    },
    "Loading manual review queue...": {
      zh: "\u6b63\u5728\u8bfb\u53d6\u672c\u5730\u4eba\u5de5\u5ba1\u6838\u961f\u5217...",
      en: "Loading manual review queue..."
    },
    "No manual review leads found.": {
      zh: "\u6682\u65e0\u5f85\u4eba\u5de5\u5ba1\u6838\u7684 YouTube \u9891\u9053\u3002",
      en: "No manual review leads found."
    },
    "Opened next manual review About page.": {
      zh: "\u5df2\u6253\u5f00\u4e0b\u4e00\u4e2a\u4eba\u5de5\u5ba1\u6838 About \u9875\u3002",
      en: "Opened next manual review About page."
    },
    "Local backend login required.": {
      zh: "\u9700\u8981\u5148\u767b\u5f55\u672c\u5730\u540e\u53f0\u3002",
      en: "Local backend login required."
    },
    "Bind the local backend account before collecting.": {
      zh: "\u8bf7\u5148\u7ed1\u5b9a\u672c\u5730\u540e\u53f0\u8d26\u53f7\uff0c\u518d\u5f00\u59cb\u91c7\u96c6\u3002",
      en: "Bind the local backend account before collecting."
    },
    "Local backend is not available.": {
      zh: "\u672c\u5730\u540e\u53f0\u4e0d\u53ef\u7528\u3002",
      en: "Local backend is not available."
    },
    "Local account heartbeat failed.": {
      zh: "\u672c\u5730\u8d26\u53f7\u5fc3\u8df3\u6821\u9a8c\u5931\u8d25\u3002",
      en: "Local account heartbeat failed."
    },
    "Local account verification is required before collecting.": {
      zh: "\u9700\u8981\u5148\u5b8c\u6210\u672c\u5730\u8d26\u53f7\u6821\u9a8c\uff0c\u518d\u5f00\u59cb\u91c7\u96c6\u3002",
      en: "Local account verification is required before collecting."
    },
    "Collecting visible email from current About dialog...": {
      zh: "\u6b63\u5728\u91c7\u96c6\u5f53\u524d About \u5f39\u7a97\u91cc\u5df2\u53ef\u89c1\u7684\u90ae\u7bb1...",
      en: "Collecting visible email from current About dialog..."
    },
    "Current page email collection failed.": {
      zh: "\u91c7\u96c6\u672c\u9875\u90ae\u7bb1\u5931\u8d25\u3002",
      en: "Current page email collection failed."
    },
    "No visible email found on current About dialog.": {
      zh: "\u5f53\u524d About \u5f39\u7a97\u6ca1\u6709\u8bfb\u5230\u5df2\u53ef\u89c1\u90ae\u7bb1\u3002",
      en: "No visible email found on current About dialog."
    },
    "Collected current page email. Uploading to local YouTube database...": {
      zh: "\u5df2\u91c7\u5230\u672c\u9875\u90ae\u7bb1\uff0c\u6b63\u5728\u4e0a\u4f20\u5230\u672c\u5730 YouTube \u6e05\u6d17\u5e93...",
      en: "Collected current page email. Uploading to local YouTube database..."
    },
    "Current page email collected and uploaded.": {
      zh: "\u672c\u9875\u90ae\u7bb1\u5df2\u91c7\u96c6\u5e76\u5165\u5e93\u3002",
      en: "Current page email collected and uploaded."
    },
    "Start failed.": {
      zh: "\u542f\u52a8\u5931\u8d25\u3002",
      en: "Start failed."
    },
    "Continue failed.": {
      zh: "\u7ee7\u7eed\u91c7\u96c6\u5931\u8d25\u3002",
      en: "Continue failed."
    },
    "No previous collection to continue. Click Start first.": {
      zh: "\u6ca1\u6709\u53ef\u7ee7\u7eed\u7684\u4e0a\u6b21\u91c7\u96c6\u7ed3\u679c\uff0c\u8bf7\u5148\u70b9\u5f00\u59cb\u91c7\u96c6\u3002",
      en: "No previous collection to continue. Click Start first."
    },
    "Continue only works on the same YouTube search results page. Click Start or Clear first.": {
      zh: "\u7ee7\u7eed\u91c7\u96c6\u53ea\u80fd\u7528\u5728\u540c\u4e00\u4e2a YouTube \u641c\u7d22\u7ed3\u679c\u9875\uff0c\u8bf7\u5148\u70b9\u5f00\u59cb\u6216\u6e05\u7a7a\u3002",
      en: "Continue only works on the same YouTube search results page. Click Start or Clear first."
    },
    "No new videos found to continue. Scroll the search page further or increase search scroll rounds.": {
      zh: "\u6ca1\u6709\u627e\u5230\u53ef\u7ee7\u7eed\u91c7\u96c6\u7684\u65b0\u89c6\u9891\uff0c\u8bf7\u628a\u641c\u7d22\u9875\u518d\u5f80\u4e0b\u6eda\u6216\u589e\u52a0\u641c\u7d22\u9875\u6eda\u52a8\u8f6e\u6b21\u3002",
      en: "No new videos found to continue. Scroll the search page further or increase search scroll rounds."
    },
    "No new videos found on this search page. Scroll the search page further or increase search scroll rounds.": {
      zh: "\u5f53\u524d\u641c\u7d22\u9875\u6ca1\u6709\u65b0\u7684\u53ef\u91c7\u89c6\u9891\uff0c\u8bf7\u4e0b\u62c9\u641c\u7d22\u9875\u6216\u589e\u52a0\u6eda\u52a8\u8f6e\u6b21\u3002",
      en: "No new videos found on this search page. Scroll the search page further or increase search scroll rounds."
    },
    "No rows to export.": {
      zh: "\u6ca1\u6709\u53ef\u5bfc\u51fa\u7684\u6570\u636e\u3002",
      en: "No rows to export."
    },
    "No manual review rows to export.": {
      zh: "\u6ca1\u6709\u9700\u8981\u4eba\u5de5\u5ba1\u67e5\u7684\u6570\u636e\u3002",
      en: "No manual review rows to export."
    },
    "Open a YouTube search results page, then start.": {
      zh: "\u5148\u6253\u5f00 YouTube \u641c\u7d22\u7ed3\u679c\u9875\uff0c\u518d\u91c7\u96c6\u535a\u4e3b\u548c\u8bc4\u8bba\u7528\u6237\u90ae\u7bb1\u3002",
      en: "Open a YouTube search results page, then collect creator and commenter emails."
    },
    "Collecting from current YouTube search results page...": {
      zh: "\u6b63\u5728\u4ece\u5f53\u524d YouTube \u641c\u7d22\u7ed3\u679c\u9875\u91c7\u96c6\u535a\u4e3b\u548c\u8bc4\u8bba\u7528\u6237\u90ae\u7bb1...",
      en: "Collecting creator and commenter emails from current YouTube search results page..."
    },
    "Manual search page collection complete.": {
      zh: "\u5f53\u524d\u641c\u7d22\u9875\u90ae\u7bb1\u91c7\u96c6\u5b8c\u6210\u3002",
      en: "Email collection complete."
    },
    "Collection complete. Uploading to local YouTube database...": {
      zh: "\u91c7\u96c6\u5b8c\u6210\uff0c\u6b63\u5728\u4e0a\u4f20\u5230\u672c\u5730 YouTube \u6e05\u6d17\u5e93...",
      en: "Collection complete. Uploading to local YouTube database..."
    },
    "Collection complete. Uploaded to local YouTube database.": {
      zh: "\u91c7\u96c6\u5b8c\u6210\uff0c\u5df2\u5165\u5e93\u5230\u672c\u5730 YouTube \u6e05\u6d17\u5e93\u3002",
      en: "Collection complete. Uploaded to local YouTube database."
    },
    "Stopped.": {
      zh: "\u5df2\u505c\u6b62\u3002",
      en: "Stopped."
    },
    "Stop requested.": {
      zh: "\u5df2\u8bf7\u6c42\u505c\u6b62\u3002",
      en: "Stop requested."
    }
  };

  const LABELS = {
    "status.idle": { zh: "\u7a7a\u95f2", en: "Idle" },
    "status.running": { zh: "\u8fd0\u884c\u4e2d", en: "Running" },
    "status.stopping": { zh: "\u505c\u6b62\u4e2d", en: "Stopping" },
    "status.stopped": { zh: "\u5df2\u505c\u6b62", en: "Stopped" },
    "status.done": { zh: "\u5b8c\u6210", en: "Done" },
    "status.error": { zh: "\u9519\u8bef", en: "Error" },
    "meta.currentSearch": { zh: "\u5f53\u524d\u641c\u7d22", en: "current search" },
    "meta.rows": { zh: "\u884c", en: "rows" },
    "table.empty": { zh: "\u6682\u65e0\u6570\u636e\u3002", en: "No rows yet." },
    "table.manualReview": { zh: "\u4eba\u5de5\u5ba1\u67e5", en: "manual review" },
    "table.noPublicEmail": { zh: "\u672a\u516c\u5f00\u90ae\u7bb1", en: "No public email" },
    "upload.none": { zh: "\u672a\u4e0a\u4f20", en: "Not uploaded" },
    "upload.uploading": { zh: "\u6b63\u5728\u5165\u5e93...", en: "Uploading to local database..." },
    "upload.incremental": { zh: "\u9010\u6761\u5165\u5e93", en: "Incremental import" },
    "upload.uploaded": { zh: "\u5df2\u5165\u5e93", en: "Uploaded" },
    "upload.error": { zh: "\u5165\u5e93\u5931\u8d25", en: "Upload failed" },
    "actor.notBound": { zh: "\u672a\u7ed1\u5b9a", en: "Not bound" },
    "actor.boundUser": { zh: "\u5df2\u7ed1\u5b9a\u7528\u6237", en: "Bound user" },
    "actor.department": { zh: "\u90e8\u95e8", en: "Department" },
    "actor.boundAt": { zh: "\u7ed1\u5b9a", en: "Bound" },
    "actor.verified": { zh: "\u5df2\u6821\u9a8c", en: "Verified" },
    "actor.checking": { zh: "\u68c0\u67e5\u4e2d", en: "Checking" },
    "actor.blocked": { zh: "\u5df2\u963b\u6b62", en: "Blocked" },
    "actor.notVerified": { zh: "\u672a\u6821\u9a8c", en: "Not verified" },
    "actor.justNow": { zh: "\u521a\u521a", en: "just now" },
    "actor.binding": { zh: "\u6b63\u5728\u7ed1\u5b9a\u5f53\u524d\u672c\u5730\u767b\u5f55\u8d26\u53f7...", en: "Binding the current local account..." },
    "actor.notBoundMessage": { zh: "\u8bf7\u5148\u767b\u5f55\u672c\u5730\u540e\u53f0\uff0c\u7136\u540e\u70b9\u51fb\u201c\u7ed1\u5b9a\u5f53\u524d\u767b\u5f55\u8d26\u53f7\u201d\u3002", en: "Log in to the local backend first, then click Bind current account." },
    "actor.loginRequired": { zh: "\u5f53\u524d\u672c\u5730\u540e\u53f0\u8fd8\u672a\u767b\u5f55\uff0c\u8bf7\u5148\u767b\u5f55\u540e\u518d\u7ed1\u5b9a\u3002", en: "The local backend is not logged in yet. Log in first, then bind again." },
    "actor.backendUnavailable": { zh: "\u672c\u5730\u540e\u53f0\u4e0d\u53ef\u7528\u3002", en: "Local backend is not available." },
    "actor.heartbeatFailed": { zh: "\u6700\u8fd1\u4e00\u6b21\u5fc3\u8df3\u672a\u901a\u8fc7\uff1a", en: "The last heartbeat was not accepted:" },
    "actor.bindFailed": { zh: "\u7ed1\u5b9a\u5931\u8d25\uff1a", en: "Bind failed:" },
    "actor.waitingHeartbeat": { zh: "\u6b63\u5728\u7b49\u5f85\u672c\u5730\u540e\u53f0\u5fc3\u8df3\u6821\u9a8c\u3002", en: "Waiting for the local backend heartbeat check." },
    "actor.heartbeatOk": { zh: "\u5fc3\u8df3\u5df2\u901a\u8fc7\u6821\u9a8c\uff08{time}\uff09\u3002\u540e\u7eed\u5fc3\u8df3\u548c\u4e0a\u4f20\u53ea\u4f1a\u5f52\u5c5e\u5230\u8fd9\u4e2a\u7528\u6237\u3002", en: "Heartbeat accepted at {time}. Uploads will be attributed only to this user." },
    "source.creator_channel": { zh: "\u535a\u4e3b\u9891\u9053", en: "Creator" },
    "source.comment_author_channel": { zh: "\u8bc4\u8bba\u7528\u6237", en: "Commenter" },
    "title": { zh: "X9 YouTube \u535a\u4e3b\u548c\u8bc4\u8bba\u7528\u6237\u90ae\u7bb1\u91c7\u96c6", en: "X9 YouTube Creator and Commenter Email Collector" }
  };

  function getLang() {
    try {
      return localStorage.getItem(KEY) === "en" ? "en" : DEFAULT_LANG;
    } catch {
      return DEFAULT_LANG;
    }
  }

  function setLang(lang) {
    const normalized = lang === "en" ? "en" : "zh";
    try {
      localStorage.setItem(KEY, normalized);
    } catch {
      // Ignore storage failures in extension previews.
    }
    apply(normalized);
    window.dispatchEvent(new CustomEvent("x9-youtube-lang-change", { detail: { lang: normalized } }));
  }

  function t(key) {
    const lang = getLang();
    return LABELS[key]?.[lang] || LABELS[key]?.en || key;
  }

  function message(value) {
    const text = String(value || "");
    const lang = getLang();
    return MESSAGES[text]?.[lang] || text;
  }

  function apply(lang = getLang()) {
    document.querySelectorAll("[data-zh][data-en]").forEach((el) => {
      el.textContent = lang === "en" ? el.getAttribute("data-en") : el.getAttribute("data-zh");
    });
    document.querySelectorAll("[data-zh-ph][data-en-ph]").forEach((el) => {
      el.setAttribute("placeholder", lang === "en" ? el.getAttribute("data-en-ph") : el.getAttribute("data-zh-ph"));
    });
    const btn = document.getElementById("langToggle");
    if (btn) {
      btn.textContent = lang === "en" ? "\u4e2d" : "EN";
      btn.title = lang === "en" ? "\u5207\u6362\u5230\u4e2d\u6587" : "Switch to English";
      btn.setAttribute("aria-label", btn.title);
    }
    document.documentElement.setAttribute("lang", lang === "en" ? "en" : "zh-CN");
    document.title = t("title");
  }

  function boot(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  window.X9YoutubeI18n = {
    getLang,
    setLang,
    apply,
    t,
    message
  };

  boot(() => {
    document.getElementById("langToggle")?.addEventListener("click", () => {
      setLang(getLang() === "en" ? "zh" : "en");
    });
    apply(getLang());
  });
})();
