const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const net = require("net");

// Range must match the "Authorized JavaScript origins" registered in
// Google Cloud Console for the OAuth client (see README_OUTREACH.md).
// Keep this small so the maintainer only has to register ~6 origins.
const PORT_RANGE_START = 8000;
const PORT_RANGE_END = 8005;

/** Probe the loopback for the first free TCP port in [start, end].
 *  Resolves with the port number; rejects if every port in range is busy. */
function findFreePort(start = PORT_RANGE_START, end = PORT_RANGE_END) {
  return new Promise((resolve, reject) => {
    let port = start;
    const tryPort = () => {
      if (port > end) {
        return reject(new Error(`no free port in [${start}-${end}]`));
      }
      const server = net.createServer();
      server.unref();
      server.once("error", (err) => {
        if (err && err.code === "EADDRINUSE") {
          port += 1;
          tryPort();
        } else {
          reject(err);
        }
      });
      server.once("listening", () => {
        const chosen = server.address().port;
        server.close(() => resolve(chosen));
      });
      server.listen(port, "127.0.0.1");
    };
    tryPort();
  });
}

class ServiceManager {
  constructor({ cwd }) {
    this.cwd = cwd;
    this.proc = null;
    this.port = null;
    this.backendUrl = null;
  }

  /** Start the FastAPI backend. Picks an available port dynamically and
   *  passes it to uvicorn via ``--port`` and to Python code via the
   *  ``BACKEND_PORT`` env var (the OAuth redirect URI builder reads it).
   *
   *  Resolves with the chosen port. Subsequent ``start()`` calls are
   *  no-ops while the process is alive.
   */
  async start() {
    if (this.proc) return this.port;

    const port = await findFreePort();
    this.port = port;
    this.backendUrl = `http://127.0.0.1:${port}`;

    const cmd = process.platform === "win32" ? "py" : "python3";
    const baseArgs = process.platform === "win32" ? ["-3.11"] : [];
    const args = [
      ...baseArgs,
      "-m", "uvicorn",
      "x9_creator_desktop_system.backend.main:app",
      "--host", "127.0.0.1",
      "--port", String(port),
    ];

    this.proc = spawn(cmd, args, {
      cwd: path.resolve(this.cwd, ".."), // parent of x9_creator_desktop_system/
      stdio: ["ignore", "inherit", "inherit"],
      shell: false,
      env: { ...process.env, BACKEND_PORT: String(port) },
    });
    this.proc.on("exit", (code) => {
      console.log(`[backend:${port}] exited with`, code);
      this.proc = null;
      this.port = null;
      this.backendUrl = null;
    });
    return port;
  }

  async stop() {
    if (!this.proc) return;
    this.proc.kill();
    this.proc = null;
    this.port = null;
    this.backendUrl = null;
  }

  async restart() {
    await this.stop();
    await new Promise((r) => setTimeout(r, 500));
    return this.start();
  }

  status() {
    return {
      running: !!this.proc,
      pid: this.proc?.pid || null,
      port: this.port,
      url: this.backendUrl,
    };
  }

  /** Poll ``/health`` until it returns 200 (or the deadline elapses). */
  waitForHealth(timeoutMs = 15000, intervalMs = 400) {
    if (!this.backendUrl) {
      return Promise.reject(new Error("backend not started"));
    }
    const url = this.backendUrl + "/health";
    const deadline = Date.now() + timeoutMs;
    return new Promise((resolve, reject) => {
      const tick = () => {
        http.get(url, (res) => {
          if (res.statusCode === 200) return resolve(true);
          schedule();
        }).on("error", schedule);
      };
      const schedule = () => {
        if (Date.now() > deadline) return reject(new Error("backend not ready"));
        setTimeout(tick, intervalMs);
      };
      tick();
    });
  }
}

module.exports = ServiceManager;
module.exports.findFreePort = findFreePort;
