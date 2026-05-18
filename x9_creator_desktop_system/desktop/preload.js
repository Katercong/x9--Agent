const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("x9desktop", {
  backendStatus: () => ipcRenderer.invoke("backend:status"),
  backendRestart: () => ipcRenderer.invoke("backend:restart"),
});
