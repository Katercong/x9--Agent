// X9 foreign-trade extension — merged background service worker.
//
// MV3 allows only ONE service worker, so we load both sub-systems' background
// logic here. Two hard rules learned the hard way:
//
//   1. importScripts() resolves relative to THIS file's location (the extension
//      ROOT), not relative to the imported file. So every path must be
//      root-relative, e.g. "social/x9_relay.js" — never a bare "x9_relay.js"
//      (which would resolve against root and fail).
//
//   2. Each importScripts is wrapped in its OWN try/catch. A throw inside a
//      try/catch does NOT prevent the service worker from registering, so the
//      extension always loads even if one sub-script is incompatible with the
//      SW context. Failures are logged individually, never block the others.
//
// recruit/background.js and the social leaf files contain no nested
// importScripts, so this flat list is the complete dependency set.

function ftLoad(path) {
  try {
    importScripts(path);
  } catch (e) {
    console.error("[X9-FT] failed to load " + path, e);
  }
}

// Shared actor identity for the foreign-trade extension.
ftLoad("ft_actor.js");

// Recruitment: side-panel behavior, backfill orchestration, native helper bridge.
ftLoad("recruit/background.js");

// Social (Xiaohongshu / Douyin): relay + collection runners.
ftLoad("social/x9_relay.js");
ftLoad("social/xhs_runner.js");
ftLoad("social/douyin_runner.js");
