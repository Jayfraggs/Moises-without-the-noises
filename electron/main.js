/**
 * Thin Electron shell -- v1 as agreed. This does exactly one job: open a
 * window pointed at the locally-running FastAPI server. No installer, no
 * icons, no auto-launching the backend itself (run.ps1/run.bat starts
 * uvicorn before this process, see the timing note below).
 *
 * When we move to full packaging, this file is where auto-launching and
 * managing the backend as a child process would go (electron-builder +
 * spawning uvicorn from app.on('ready') instead of relying on run.ps1).
 * Deliberately not building that yet per the "thin shell first" decision.
 */

const { app, BrowserWindow } = require('electron');

const BACKEND_URL = 'http://localhost:8000';
const MAX_RETRIES = 15;
const RETRY_DELAY_MS = 1000;

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#14161a', // matches --bg in App.css; avoids a white
                                 // flash before the page's own styles load
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  loadWithRetry(win, MAX_RETRIES);
}

/**
 * run.ps1/run.bat start uvicorn and then immediately launch Electron --
 * uvicorn's startup (importing torch, etc.) is not instant, so the backend
 * may not be accepting connections yet on Electron's first load attempt.
 * Rather than adding a fixed sleep to the shell scripts (fragile: too
 * short and this races anyway, too long and every launch is slower than
 * necessary), retry the load here with backoff until the backend answers.
 */
function loadWithRetry(win, retriesLeft) {
  win.loadURL(BACKEND_URL).catch(() => {
    if (retriesLeft <= 0) {
      win.loadURL(
        `data:text/html,<body style="background:#14161a;color:#edeae3;` +
          `font-family:sans-serif;padding:40px">` +
          `<h2>Backend didn't start</h2>` +
          `<p>Couldn't reach ${BACKEND_URL} after ${MAX_RETRIES} attempts. ` +
          `Check the terminal window for uvicorn errors.</p></body>`
      );
      return;
    }
    setTimeout(() => loadWithRetry(win, retriesLeft - 1), RETRY_DELAY_MS);
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
