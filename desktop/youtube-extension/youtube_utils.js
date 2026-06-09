(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.X9YoutubeUtils = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function searchResultsUrl(keyword) {
    return `https://www.youtube.com/results?search_query=${encodeURIComponent(String(keyword || "").trim())}`;
  }

  function extractVideoId(url) {
    try {
      const parsed = new URL(url, "https://www.youtube.com");
      if (parsed.pathname.startsWith("/shorts/")) return parsed.pathname.split("/").filter(Boolean)[1] || "";
      if (parsed.hostname === "youtu.be") return parsed.pathname.split("/").filter(Boolean)[0] || "";
      return parsed.searchParams.get("v") || "";
    } catch {
      return "";
    }
  }

  function normalizeVideoUrl(url) {
    try {
      const parsed = new URL(url, "https://www.youtube.com");
      const id = extractVideoId(parsed.toString());
      if (!id) return "";
      if (parsed.pathname.startsWith("/shorts/")) return `https://www.youtube.com/shorts/${id}`;
      return `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
    } catch {
      return "";
    }
  }

  function detectContentType(url) {
    try {
      const parsed = new URL(url, "https://www.youtube.com");
      if (parsed.pathname.startsWith("/shorts/")) return "shorts";
      if (parsed.pathname.startsWith("/watch") || parsed.searchParams.get("v")) return "video";
      return "";
    } catch {
      return "";
    }
  }

  function normalizeChannelUrl(url) {
    try {
      const parsed = new URL(url, "https://www.youtube.com");
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (!parts.length) return "";
      if (parts[0].startsWith("@")) return `${parsed.origin}/${decodePathPart(parts[0])}`;
      if (["channel", "c", "user"].includes(parts[0]) && parts[1]) {
        return `${parsed.origin}/${parts[0]}/${decodePathPart(parts[1])}`;
      }
      return "";
    } catch {
      return "";
    }
  }

  function channelAboutUrl(url) {
    const normalized = normalizeChannelUrl(url);
    if (!normalized) return "";
    return `${normalized.replace(/\/+$/, "")}/about`;
  }

  function channelHomeUrl(url) {
    return normalizeChannelUrl(url);
  }

  function channelVideosUrl(url) {
    const normalized = normalizeChannelUrl(url);
    if (!normalized) return "";
    return `${normalized.replace(/\/+$/, "")}/videos`;
  }

  function extractChannelHandle(url) {
    try {
      const firstPart = decodePathPart(new URL(normalizeChannelUrl(url) || url).pathname.split("/").filter(Boolean)[0] || "");
      return firstPart.startsWith("@") ? firstPart : "";
    } catch {
      return "";
    }
  }

  function extractChannelId(url) {
    try {
      const parts = new URL(normalizeChannelUrl(url) || url).pathname.split("/").filter(Boolean);
      return parts[0] === "channel" ? decodePathPart(parts[1] || "") : "";
    } catch {
      return "";
    }
  }

  function isYoutubeUrl(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      return host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be";
    } catch {
      return false;
    }
  }

  function dedupeBy(items, keyFn) {
    const seen = new Set();
    const out = [];
    for (const item of items || []) {
      const key = keyFn(item);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  }

  function decodePathPart(value) {
    try {
      return decodeURIComponent(value || "");
    } catch {
      return value || "";
    }
  }

  return {
    searchResultsUrl,
    extractVideoId,
    normalizeVideoUrl,
    detectContentType,
    normalizeChannelUrl,
    channelHomeUrl,
    channelAboutUrl,
    channelVideosUrl,
    extractChannelHandle,
    extractChannelId,
    isYoutubeUrl,
    dedupeBy
  };
});
