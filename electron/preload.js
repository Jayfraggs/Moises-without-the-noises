/**
 * preload.js
 *
 * Bridge between the Electron main process (IPC handlers) and the renderer process (React app).
 * Exposes safe IPC methods to window.electronAPI for use in components.
 *
 * With contextIsolation: true, the renderer process cannot directly access Node APIs.
 * This preload script runs in the main process but with access to the DOM, allowing us to
 * expose specific IPC methods in a controlled manner.
 */

const { contextBridge, ipcRenderer, shell } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Drive detection and configuration
  detectDrive: () => ipcRenderer.invoke('drive:detect'),
  getDriveConfig: () => ipcRenderer.invoke('drive:getConfig'),
  setDriveConfig: (drivePath, mwtnFolder) =>
    ipcRenderer.invoke('drive:setConfig', drivePath, mwtnFolder),

  // File dialogs
  selectFolder: () => ipcRenderer.invoke('dialog:selectFolder'),
  
  // File system
  listFolder: (folderPath) => ipcRenderer.invoke('fs:listFolder', folderPath),
  joinPath: (...args) => ipcRenderer.invoke('fs:joinPath', ...args),

  // External links (uses shell.openExternal for security)
  openExternal: (url) => {
    // Validate URL to prevent malicious links
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return shell.openExternal(url);
      }
    } catch (error) {
      console.error('Invalid URL:', url, error);
    }
  },
});
