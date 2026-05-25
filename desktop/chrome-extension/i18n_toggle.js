/* Unified Chinese / English toggle for the popup + side panel.
 *
 * Elements get translated content via data-zh / data-en attributes (and
 * data-zh-ph / data-en-ph for placeholder text on inputs). The toggle
 * button reads `localStorage.tsclbLang` to remember the user's choice.
 */
(function () {
  const KEY = "tsclbLang";
  function getLang() {
    try { return localStorage.getItem(KEY) === "en" ? "en" : "zh"; } catch (_) { return "zh"; }
  }
  function setLang(lang) {
    try { localStorage.setItem(KEY, lang); } catch (_) {}
    apply(lang);
  }
  function apply(lang) {
    document.querySelectorAll("[data-zh][data-en]").forEach((el) => {
      el.textContent = lang === "en" ? el.getAttribute("data-en") : el.getAttribute("data-zh");
    });
    document.querySelectorAll("[data-zh-ph][data-en-ph]").forEach((el) => {
      el.setAttribute("placeholder", lang === "en" ? el.getAttribute("data-en-ph") : el.getAttribute("data-zh-ph"));
    });
    const btn = document.getElementById("langToggle");
    if (btn) btn.textContent = lang === "en" ? "中" : "EN";
    document.documentElement.setAttribute("lang", lang === "en" ? "en" : "zh-CN");

    // Hook into the legacy popup.js i18n select so the (hidden) X9 panel
    // also flips, keeping internal state coherent.
    try {
      const sel = document.getElementById("languageSelect");
      if (sel && sel.value !== lang) {
        sel.value = lang;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      }
    } catch (_) { /* ignore */ }
  }
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("langToggle");
    if (btn) {
      btn.addEventListener("click", () => setLang(getLang() === "en" ? "zh" : "en"));
    }
    apply(getLang());
  });
})();
