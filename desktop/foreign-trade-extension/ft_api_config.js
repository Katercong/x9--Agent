// X9 foreign-trade extension — shared config + ingest fetch shim.
//
// Loaded after ft_actor.js (which carries the per-user department_code) in every
// content-script list and in the side panels. It:
//   1. points both sub-systems' API base at the local X9 desktop backend, and
//   2. wraps fetch() so every ingest POST automatically carries department_code
//      + actor identity — cross-origin pushes get no session cookie, so the
//      department must travel in the payload. This avoids editing each vendored
//      collector (job_collector / qzrc / xhs / douyin) individually.
(function () {
  var BASE = "http://127.0.0.1:8000";
  var actor = (typeof globalThis !== "undefined" && globalThis.__X9_FT_ACTOR__) || {};
  var dept = actor.department_code || "foreign_trade";

  // Recruitment collectors read this for their API base.
  try { window.__COMPANYLEADS_API_BASE__ = BASE; } catch (e) {}
  // XHS / Douyin collectors read this.
  try { window.__X9_XHS_BASE__ = BASE; } catch (e) {}
  try { window.__X9_FT__ = { base: BASE, department_code: dept, actor_user_id: actor.actor_user_id || "" }; } catch (e) {}

  // Ingest paths the wrapper should enrich (X9 compat + native endpoints).
  var INGEST_HINT = /\/api\/(companies|talents|xhs|douyin|local\/(company-leads|talents|xhs))\//;

  if (typeof window !== "undefined" && typeof window.fetch === "function" && !window.__X9_FT_FETCH_PATCHED__) {
    var origFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      try {
        var url = typeof input === "string" ? input : (input && input.url) || "";
        if (url && INGEST_HINT.test(url) && init && typeof init.body === "string") {
          var body = JSON.parse(init.body);
          if (body && typeof body === "object" && !Array.isArray(body)) {
            if (!body.department_code) body.department_code = dept;
            if (!body.actor_user_id && actor.actor_user_id) body.actor_user_id = actor.actor_user_id;
            init = Object.assign({}, init, { body: JSON.stringify(body) });
          }
        }
      } catch (e) { /* never block the request on enrichment failure */ }
      return origFetch(input, init);
    };
    window.__X9_FT_FETCH_PATCHED__ = true;
  }
})();
