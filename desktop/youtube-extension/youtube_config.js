var X9_YOUTUBE_BACKEND_CONFIG = {
  mode: "local",
  localBaseUrl: "http://127.0.0.1:8000",
  productionBaseUrl: "https://usx9.us",
  identityMode: "local",
  localIdentityBaseUrl: "http://127.0.0.1:8000",
  productionIdentityBaseUrl: "https://usx9.us"
};

function getX9YoutubeBackendBaseUrl() {
  const config = self.X9_YOUTUBE_BACKEND_CONFIG || X9_YOUTUBE_BACKEND_CONFIG;
  const mode = String(config.mode || "local").toLowerCase();
  const base = mode === "production" ? config.productionBaseUrl : config.localBaseUrl;
  return String(base || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

function getX9YoutubeIdentityBaseUrl() {
  const config = self.X9_YOUTUBE_BACKEND_CONFIG || X9_YOUTUBE_BACKEND_CONFIG;
  const mode = String(config.identityMode || config.mode || "local").toLowerCase();
  const base = mode === "production" ? config.productionIdentityBaseUrl : config.localIdentityBaseUrl;
  return String(base || "http://127.0.0.1:8000").replace(/\/+$/, "");
}
