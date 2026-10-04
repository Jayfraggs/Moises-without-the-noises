/**
 * app.js — mwtn frontend entry point.
 *
 * Vanilla JS, no framework. Talks to the FastAPI backend at /api/*.
 *
 * Architecture:
 *   state.js     — all mutable state, single source of truth
 *   api.js       — fetch wrappers for the backend
 *   catalog.js   — library list rendering + song selection
 *   studio.js    — waveform + mixer setup after a song loads
 *   transport.js — play/pause/seek/loop/speed/pitch controls
 *   import.js    — file drop, ZIP upload, ingest polling
 *   extract.js   — extract configuration modal (model + stem selection)
 *   settings.js  — settings dialog + drive scan
 */

import { State }    from './state.js';
import { API }      from './api.js';
import { Catalog }  from './catalog.js';
import { Studio }   from './studio.js';
import { Transport } from './transport.js';
import { Import }   from './import.js';
import { Extract }  from './extract.js';
import { Settings }   from './settings.js';
import { SolfaPanel } from './solfa.js';

// ── Globals accessible in DevTools ───────────────────────────────────────────
window._mwtn = { State, API };

// ── Boot ─────────────────────────────────────────────────────────────────────
async function boot() {
  console.log('[mwtn] booting…');

  // Wire all modules
  const catalog    = new Catalog({ State, API, Studio });
  const studio     = new Studio({ State, API });
  const transport  = new Transport({ State, studio });
  const importer   = new Import({ State, API, catalog });
  const extract    = new Extract({ API });
  const settings   = new Settings({ State, API, catalog });
  const solfaPanel = new SolfaPanel({ API });

  // Make studio reachable from catalog
  catalog.studio = studio;

  // Hook SolfaPanel into Studio's rAF loop
  studio._onTick = (pos) => solfaPanel.tick(pos);

  // Hook SolfaPanel load alongside studio loadSong
  const _origLoad = studio.loadSong.bind(studio);
  studio.loadSong = async (songId) => {
    solfaPanel.clear();
    await _origLoad(songId);
    // Only load solfa if the song has a bass stem
    const manifest = State.manifest;
    if (manifest?.stems?.includes('bass')) {
      solfaPanel.loadSong(songId);
    }
  };

  // Allow solfège cells to seek the player
  document.addEventListener('solfa:seek', (e) => {
    studio.seek(e.detail.time);
  });

  // Solfa panel collapse toggle
  const solfaCollapseBtn = document.getElementById('solfaCollapseBtn');
  const solfaBody        = document.getElementById('solfaBody');
  solfaCollapseBtn?.addEventListener('click', () => {
    const expanded = solfaCollapseBtn.getAttribute('aria-expanded') === 'true';
    solfaCollapseBtn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    if (solfaBody) solfaBody.style.display = expanded ? 'none' : '';
    const chevron = solfaCollapseBtn.querySelector('svg polyline');
    if (chevron) chevron.setAttribute('points', expanded ? '6 9 12 15 18 9' : '18 15 12 9 6 15');
  });

  // Start
  await catalog.load();
  transport.init();
  importer.init();
  await extract.init();
  settings.init();

  // Panel toggles (Analysis / Sections)
  document.querySelectorAll('.daw-panel-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const panel = btn.dataset.panel;
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', pressed ? 'false' : 'true');
      const el = panel === 'analysis'
        ? document.getElementById('transport')
        : document.querySelector('.daw-section-ribbon');
      if (el) el.style.display = pressed ? 'none' : '';
    });
  });

  // Sidebar collapse
  const collapseBtn = document.getElementById('sidebarCollapseBtn');
  const sidebar = document.getElementById('catalogPanel');
  collapseBtn?.addEventListener('click', () => {
    const expanded = collapseBtn.getAttribute('aria-expanded') === 'true';
    collapseBtn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    sidebar?.classList.toggle('collapsed', expanded);
  });

  // Import button opens file picker
  document.getElementById('importBtn')?.addEventListener('click', () => {
    document.getElementById('fileInput')?.click();
  });

  // Upload btn
  document.getElementById('uploadFileBtn')?.addEventListener('click', () => {
    document.getElementById('fileInput')?.click();
  });

  // Export panel toggle
  const exportBtn   = document.getElementById('t-export-btn');
  const exportPanel = document.getElementById('t-export-panel');
  exportBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = exportPanel?.classList.toggle('hidden') === false;
    exportBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  document.addEventListener('click', () => exportPanel?.classList.add('hidden'));

  // Export actions
  document.getElementById('t-export-mix')?.addEventListener('click', () => {
    studio.exportMix();
    exportPanel?.classList.add('hidden');
  });
  document.getElementById('t-export-stems')?.addEventListener('click', () => {
    studio.exportStems();
    exportPanel?.classList.add('hidden');
  });

  // Metro volume popover
  const metroVolBtn   = document.getElementById('t-metro-vol-btn');
  const metroVolPanel = document.getElementById('t-metro-vol-panel');
  metroVolBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    metroVolPanel?.classList.toggle('hidden');
  });
  document.addEventListener('click', () => metroVolPanel?.classList.add('hidden'));

  console.log('[mwtn] ready');
}

boot().catch(err => {
  console.error('[mwtn] boot failed:', err);
  const errEl = document.getElementById('error');
  if (errEl) {
    errEl.textContent = `Failed to start: ${err.message}`;
    errEl.classList.remove('hidden');
  }
});
