// Electron main process — spawns the python backend on a dynamically
// chosen free port (8000 → 8020), polls /health, and opens a
// BrowserWindow on the FastAPI-served /ui/ page.
const { app, BrowserWindow, ipcMain, Menu } = require("electron");
const path = require("path");
const ServiceManager = require("./service_manager");

let win;
const sm = new ServiceManager({
  cwd: path.resolve(__dirname, ".."),
});

async function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    title: "X9 Creator Desktop",
    backgroundColor: "#0f1115",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  Menu.setApplicationMenu(null);
  // Splash while we wait for the backend.
  win.loadFile(path.join(__dirname, "splash.html")).catch(() => {});

  try {
    const port = await sm.start();
    console.log(`[main] backend bound to port ${port}`);
    await sm.waitForHealth();
    win.loadURL(sm.backendUrl + "/ui/");
  } catch (err) {
    console.error("[main] backend failed to start:", err);
    // Surface the error in the splash so the user isn't stuck staring
    // at it forever.
    win.webContents
      .executeJavaScript(
        `document.body.innerHTML = '<div style="color:#fecaca;padding:24px;font:14px system-ui">` +
        `Backend failed to start: ${String(err.message || err).replace(/'/g, "\\'")}` +
        `</div>'`
      )
      .catch(() => {});
  }
}

ipcMain.handle("backend:status", () => sm.status());
ipcMain.handle("backend:restart", async () => {
  const port = await sm.restart();
  await sm.waitForHealth();
  if (win) win.loadURL(sm.backendUrl + "/ui/");
  return { ...sm.status(), restarted: true };
});

app.whenReady().then(createWindow);
app.on("window-all-closed", async () => {
  await sm.stop();
  if (process.platform !== "darwin") app.quit();
});

// Best-effort cleanup if the user kills Electron with Ctrl+C / closes via
// task manager — make sure the python child doesn't get orphaned.
process.on("SIGINT", async () => { await sm.stop(); process.exit(0); });
process.on("SIGTERM", async () => { await sm.stop(); process.exit(0); });
