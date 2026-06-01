// X9 foreign-trade extension — actor identity (rewritten at download time).
//
// The X9 backend /api/local/extension/download replaces this file with the
// logged-in user's actor + department_code. It runs in the content-script
// isolated world AND in the side-panel pages, so both the page collectors and
// the panel uploaders can stamp ingested leads with the right department.
//
// Default below is used only if an un-personalized copy is loaded; since this
// is the foreign-trade plugin, foreign_trade is the safe default.
globalThis.__X9_FT_ACTOR__ = {
  department_code: "foreign_trade",
  actor_user_id: "",
  actor_token: ""
};
