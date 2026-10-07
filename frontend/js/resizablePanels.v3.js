const STORAGE_KEY = 'mwtn.panel-heights.v1';
const DEFAULT_HEIGHTS = { harmonicPanel: 190, solfaPanel: 140, lyricsPanel: 150 };

function readHeights() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}

function clamp(value, panel) {
  if (!panel) return value;
  const minimum = Number(panel.getAttribute('data-min-height') || 72);
  const maximum = Math.max(minimum, Math.floor(window.innerHeight * 0.7));
  return Math.min(maximum, Math.max(minimum, value));
}

function applyHeight(panel, height) {
  const value = clamp(height, panel);
  panel.style.setProperty('--user-panel-height', `${value}px`);
  panel.style.height = `${value}px`;
  panel.setAttribute('data-panel-height', String(value));
}

function addHandle(panel, heights) {
  if (!panel) return;
  if (panel.querySelector(':scope > .panel-resize-handle')) return;
  panel.classList.add('user-resizable-panel');
  const saved = Number(heights[panel.id]) || DEFAULT_HEIGHTS[panel.id];
  if (saved) applyHeight(panel, saved);

  const handle = document.createElement('button');
  handle.type = 'button';
  handle.className = 'panel-resize-handle';
  handle.setAttribute('aria-label', `Resize ${panel.getAttribute('aria-label') || panel.id}`);
  handle.title = 'Drag to resize; double-click to reset';
  panel.prepend(handle);

  let startY = 0;
  let startHeight = 0;
  const finish = () => {
    document.body.classList.remove('is-resizing-panel');
    const next = { ...readHeights(), [panel.id]: Number(panel.getAttribute('data-panel-height')) };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  };
  handle.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    startY = event.clientY;
    startHeight = panel.getBoundingClientRect().height;
    document.body.classList.add('is-resizing-panel');
  });
  handle.addEventListener('pointermove', (event) => {
    if (!handle.hasPointerCapture(event.pointerId)) return;
    applyHeight(panel, startHeight + event.clientY - startY);
  });
  handle.addEventListener('pointerup', finish);
  handle.addEventListener('pointercancel', finish);
  handle.addEventListener('dblclick', () => {
    applyHeight(panel, DEFAULT_HEIGHTS[panel.id]);
    const next = readHeights(); delete next[panel.id];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  });
  handle.addEventListener('keydown', (event) => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    applyHeight(panel, panel.getBoundingClientRect().height + (event.key === 'ArrowDown' ? 16 : -16));
    finish();
  });
  // Some panels redraw their inner markup. Keep the resize affordance outside
  // that redraw lifecycle without coupling the panel renderer to this module.
  const observer = new MutationObserver(() => {
    if (!panel.querySelector(':scope > .panel-resize-handle')) panel.prepend(handle);
  });
  observer.observe(panel, { childList: true });
}

export function initResizablePanels() {
  const heights = readHeights();
  ['harmonicPanel', 'solfaPanel', 'lyricsPanel'].forEach((id) => {
    const panel = document.getElementById(id);
    if (panel) addHandle(panel, heights);
  });
}
