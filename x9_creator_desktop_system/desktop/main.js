const { app, BrowserWindow, ipcMain, Menu } = require("electron");
const path = require("path");
const ServiceManager = require("./service_manager");

let win;
const sm = new ServiceManager();

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
  win.loadFile(path.join(__dirname, "splash.html")).catch(() => {});

  try {
    await sm.start();
    console.log(`[main] backend: ${sm.backendUrl}`);
    await sm.waitForHealth();
    win.loadURL(sm.backendUrl + "/portal/");
  } catch (err) {
    console.error("[main] backend failed:", err);
    win.webContents
      .executeJavaScript(
        `document.body.innerHTML = '<div style="color:#fecaca;padding:24px;font:14px system-ui">` +
        `Backend unavailable: ${String(err.message || err).replace(/'/g, "\\'")}` +
        `</div>'`
      )
      .catch(() => {});
  }
}

ipcMain.handle("backend:status", () => sm.status());
ipcMain.handle("backend:restart", async () => {
  await sm.restart();
  await sm.waitForHealth();
  if (win) win.loadURL(sm.backendUrl + "/portal/");
  return { ...sm.status(), restarted: true };
});

app.whenReady().then(createWindow);
app.on("window-all-closed", async () => {
  await sm.stop();
  if (process.platform !== "darwin") app.quit();
});

process.on("SIGINT", async () => { await sm.stop(); process.exit(0); });
process.on("SIGTERM", async () => { await sm.stop(); process.exit(0); });
