(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.X9YoutubeContact = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
  const EMAIL_VALID_RE = /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i;
  const OBFUSCATED_EMAIL_RE = /\b([A-Z0-9._%+-]+)\s*(?:\[\s*at\s*\]|\(\s*at\s*\))\s*([A-Z0-9-]+(?:\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\))\s*[A-Z0-9-]+)+)\b/gi;
  const OBFUSCATED_DOT_RE = /\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\))\s*/gi;
  const WHATSAPP_URL_RE = /\b(?:https?:\/\/)?(?:www\.)?(?:wa\.me\/|api\.whatsapp\.com\/send\?phone=)(\+?\d[\d\s().-]{5,}\d)\b/gi;
  const WHATSAPP_LABEL_RE = /\b(?:whats\s*app|whatsapp|wa)\s*(?:[:=]|id|phone|number)?\s*(\+?\d[\d\s().-]{7,}\d)\b/gi;
  const INSTAGRAM_URL_RE = /\b(?:https?:\/\/)?(?:www\.)?instagram\.com\/([A-Za-z0-9._]{2,30})\/?\b/gi;
  const INSTAGRAM_LABEL_RE = /\b(?:instagram|insta|ig)\s*(?:[:=]|@|handle|id)\s*@?([A-Za-z0-9._]{2,30})\b/gi;
  const WECHAT_RE = /(?:wechat|weixin|\bwx\b|\u5fae\u4fe1)\s*(?:[:=\-]|\uff1a)?\s*([A-Za-z][A-Za-z0-9_-]{5,19})\b/gi;
  const URL_RE = /\b(?:https?:\/\/[^\s<>"')]+|(?:linktr\.ee|beacons\.ai|bio\.site|msha\.ke|solo\.to|stan\.store|campsite\.bio)\/[^\s<>"')]+)/gi;

  const FAKE_EMAILS = new Set([
    "example@example.com",
    "test@test.com",
    "name@example.com",
    "yourname@email.com"
  ]);

  const BLOCKED_URL_HOSTS = new Set([
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "google.com",
    "www.google.com",
    "gstatic.com",
    "www.gstatic.com"
  ]);

  function detectContacts(input) {
    const text = normalizeText(input);
    if (!text) return [];

    const contacts = [];
    collectEmails(text, contacts);
    collectWhatsApp(text, contacts);
    collectInstagram(text, contacts);
    collectWeChat(text, contacts);
    collectWebsites(text, contacts);
    return dedupeContacts(contacts);
  }

  function collectEmails(text, contacts) {
    for (const match of text.matchAll(EMAIL_RE)) {
      const value = match[0].toLowerCase();
      if (FAKE_EMAILS.has(value)) continue;
      contacts.push(contact("email", value, text, match.index || 0));
    }
    for (const match of text.matchAll(OBFUSCATED_EMAIL_RE)) {
      const value = normalizeObfuscatedEmail(match[1], match[2]);
      if (!value || FAKE_EMAILS.has(value)) continue;
      contacts.push(contact("email", value, text, match.index || 0));
    }
  }

  function collectWhatsApp(text, contacts) {
    for (const match of text.matchAll(WHATSAPP_URL_RE)) {
      const phone = normalizePhone(match[1]);
      if (isLikelyPhone(phone)) {
        contacts.push(contact("whatsapp", phone, text, match.index || 0));
      }
    }
    for (const match of text.matchAll(WHATSAPP_LABEL_RE)) {
      const phone = normalizePhone(match[1]);
      if (isLikelyPhone(phone)) {
        contacts.push(contact("whatsapp", phone, text, match.index || 0));
      }
    }
  }

  function collectInstagram(text, contacts) {
    for (const match of text.matchAll(INSTAGRAM_URL_RE)) {
      const handle = cleanHandle(match[1]);
      if (isValidSocialHandle(handle)) {
        contacts.push(contact("instagram", "@" + handle, text, match.index || 0));
      }
    }
    for (const match of text.matchAll(INSTAGRAM_LABEL_RE)) {
      const handle = cleanHandle(match[1]);
      if (isValidSocialHandle(handle)) {
        contacts.push(contact("instagram", "@" + handle, text, match.index || 0));
      }
    }
  }

  function collectWeChat(text, contacts) {
    for (const match of text.matchAll(WECHAT_RE)) {
      const value = cleanToken(match[1]);
      if (isValidWechatId(value)) {
        contacts.push(contact("wechat", value, text, match.index || 0));
      }
    }
  }

  function collectWebsites(text, contacts) {
    for (const match of text.matchAll(URL_RE)) {
      const value = normalizeUrl(match[0]);
      if (!value || isBlockedUrl(value)) continue;
      if (/instagram\.com/i.test(value) || /(?:wa\.me|whatsapp\.com)/i.test(value)) continue;
      contacts.push(contact("website", value, text, match.index || 0));
    }
  }

  function contact(type, value, text, index) {
    return {
      type,
      value,
      evidence_text: makeSnippet(text, index)
    };
  }

  function dedupeContacts(contacts) {
    const seen = new Set();
    const out = [];
    for (const item of contacts) {
      const key = `${item.type}:${String(item.value || "").toLowerCase()}`;
      if (!item.value || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  }

  function normalizeText(input) {
    return String(input || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+/g, " ")
      .trim();
  }

  function normalizeObfuscatedEmail(localPart, domainPart) {
    const local = String(localPart || "").trim().toLowerCase();
    const domain = String(domainPart || "")
      .replace(OBFUSCATED_DOT_RE, ".")
      .replace(/\s+/g, "")
      .toLowerCase();
    const value = `${local}@${domain}`;
    return EMAIL_VALID_RE.test(value) ? value : "";
  }

  function normalizePhone(value) {
    const raw = String(value || "").trim();
    const plus = raw.startsWith("+") ? "+" : "";
    return plus + raw.replace(/[^\d]/g, "");
  }

  function isLikelyPhone(value) {
    const digits = String(value || "").replace(/[^\d]/g, "");
    return digits.length >= 8 && digits.length <= 16;
  }

  function cleanHandle(value) {
    return cleanToken(value).replace(/^@+/, "");
  }

  function cleanToken(value) {
    return String(value || "").replace(/[.,;:!?/\\)\]}]+$/g, "").trim();
  }

  function isValidSocialHandle(value) {
    if (!/^[A-Za-z0-9._]{2,30}$/.test(value || "")) return false;
    return !/^(com|www|http|https|instagram|insta|handle|profile)$/i.test(value);
  }

  function isValidWechatId(value) {
    return /^[A-Za-z][A-Za-z0-9_-]{5,19}$/.test(value || "");
  }

  function normalizeUrl(value) {
    let raw = cleanToken(value);
    if (!raw) return "";
    if (!/^https?:\/\//i.test(raw)) raw = "https://" + raw;
    try {
      const url = new URL(raw);
      url.hash = "";
      return url.toString().replace(/\/$/, "");
    } catch {
      return "";
    }
  }

  function isBlockedUrl(value) {
    try {
      const host = new URL(value).hostname.toLowerCase();
      if (BLOCKED_URL_HOSTS.has(host)) return true;
      return Array.from(BLOCKED_URL_HOSTS).some((blocked) => host.endsWith("." + blocked));
    } catch {
      return true;
    }
  }

  function makeSnippet(text, index) {
    const start = Math.max(0, index - 70);
    const end = Math.min(text.length, index + 110);
    return text.slice(start, end).replace(/\s+/g, " ").trim();
  }

  return {
    detectContacts,
    normalizeText,
    normalizeUrl
  };
});
