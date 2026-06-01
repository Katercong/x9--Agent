// Placeholder. The X9 backend /api/local/extension/download rewrites this file
// at download time with the logged-in user's actor + department_code:
//   globalThis.X9_BUNDLED_ACTOR_CONFIG = {ok, actor_user_id, actor:{...,department_code}, actor_token, ...}
// ft_api_config.js reads it to stamp ingested leads with the right department.
globalThis.X9_BUNDLED_ACTOR_CONFIG = { ok: false, source: "placeholder" };
