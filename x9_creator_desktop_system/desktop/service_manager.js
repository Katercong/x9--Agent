const https = require("https");

const REMOTE_BACKEND_URL = (process.env.X9_REMOTE_BACKEND_URL || "https://usx9.us").replace(/\/+$/, "");

class ServiceManager {
  constructor() {
    this.backendUrl = REMOTE_BACKEND_URL;
  }

  async start() {
    return this.backendUrl;
  }

  async stop() {
    return undefined;
  }

  async restart() {
    return this.start();
  }

  status() {
    return {
      running: true,
      pid: null,
      port: null,
      url: this.backendUrl,
      remote: true,
    };
  }

  waitForHealth(timeoutMs = 15000, intervalMs = 400) {
    const url = this.backendUrl + "/health";
    const deadline = Date.now() + timeoutMs;
    return new Promise((resolve, reject) => {
      const tick = () => {
        const req = https.get(url, (res) => {
          res.resume();
          if (res.statusCode === 200) return resolve(true);
          schedule();
        });
        req.on("error", schedule);
        req.setTimeout(intervalMs, () => {
          req.destroy();
          schedule();
        });
      };
      const schedule = () => {
        if (Date.now() > deadline) return reject(new Error("remote backend not ready"));
        setTimeout(tick, intervalMs);
      };
      tick();
    });
  }
}

module.exports = ServiceManager;
