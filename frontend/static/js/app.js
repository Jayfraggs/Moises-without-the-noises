/**
 * app.js — mwtn frontend entry point.
 *  *
 * Vanilla JS, no framework. Talks to the FastAPI backend at /api/*.
 *
 * Architecture:
 *   state.js     — all mutable state, single source of truth
 *   api.js       — fetch wrappers for the backend
 *   catalog.js   — library list rendering + song selection
 *   studio.js    — waveform + mixer setup after a song loads
 *   transport.js — play/pause/seek/loop/speed/pitch controls
 *   import.js    — file drop, ZIP upload, ingest polling, local separation
 *   extract.js   — extraction settings modal (model + stem selection)
 *   settings.js  — settings dialog + drive scan
 *   solfa.js     — bass solfège panel with playback sync
 *   lyrics.js    — synced lyrics panel with playback sync
 */
 
import { State }      from './state.js';
import { API }        from './api.js';
import { Catalog }    from './catalog.js';
import { Studio }     from './studio.js';
import { Transport }  from './transport.js';
import { Import }     from './import.js';
import { Settings }   from './settings.js';
import { SolfaPanel } from './solfa.js';
import { LyricsPanel } from './lyrics.js';
import { BeatGrid }   from './beat-grid.js';
import { Sections }   from './sections.js';
import { VuMeters }   from './vu-meters.js';
import { HarmonicPanel } from './harmonic.v2.js';
import { initResizablePanels } from './resizablePanels.v3.js';
import { initExtractPanel } from './ui/extractPanel.js';

window._mwtn = { State, API };

async function boot() {
  try { State.solfa_colours = JSON.parse(localStorage.getItem('mwtn_extract_settings') || '{}').solfa_colours ?? true; } catch { State.solfa_colours = true; }
  console.log('[mwtn] booting…');
  initResizablePanels();

  const studio     = new Studio({ State, API });
  window._mwtn._studio = studio;
  const catalog    = new Catalog({ State, API, Studio });
  const transport  = new Transport({ State, studio });
  const importer   = new Import({ State, API, catalog });
  const settings   = new Settings({ State, API, catalog });
  const solfaPanel = new SolfaPanel({ API });
  const lyricsPanel = new LyricsPanel({ API });
  const beatGrid   = new BeatGrid({ State, API, studio });
  const sections   = new Sections({ State, API, studio });
  const vuMeters   = new VuMeters({ studio });
  const harmonic   = new HarmonicPanel({ State, API });
  harmonic.init();

  catalog.studio = studio;

  // ── Wire studio hooks ─────────────────────────────────────────────────────

  studio._onTick = (pos) => {
    solfaPanel.tick(pos);
    lyricsPanel.tick(pos);
    beatGrid.tick(pos);
    sections.tick(pos);
    harmonic.tick(pos);
  };

  studio._onStemReady = (name, total, loaded) => {
    vuMeters.rebuild();
    _updateExportPerStemPanel();
  };

  // Wrap loadSong to trigger panel resets + post-load population
  const _origLoad = studio.loadSong.bind(studio);
  studio.loadSong = async (songId) => {
    solfaPanel.clear();
    lyricsPanel.clear();
    beatGrid.clear();
    sections.clear();
    vuMeters.stop();

    await _origLoad(songId);

    harmonic.loadSong(songId);

    beatGrid.loadSong(songId);
    sections.loadSong(songId);
    lyricsPanel.loadSong(songId);
    vuMeters.rebuild();
    vuMeters.start();
    _updateExportPerStemPanel();
    _updateVocalSplitUI();

    if (State.manifest?.stems?.includes('bass')) solfaPanel.loadSong(songId, 'bass');
  };

  function _updateVocalSplitUI() {
    const stems = State.manifest?.stems || [];
    const hasVocals       = stems.includes('vocals');
    const hasLeadVocals   = stems.includes('lead_vocals');
    const hasBackingVocals = stems.includes('backing_vocals');
    const splitDone = hasLeadVocals || hasBackingVocals;

    // Show/hide the trigger row
    const splitRow = document.getElementById('vocalSplitRow');
    if (splitRow) splitRow.classList.toggle('hidden', !hasVocals || splitDone);

    // Show/hide the static lane stubs (studio will also render dynamic lanes)
    document.querySelector('.lead_vocals')?.classList.toggle('hidden', !hasLeadVocals);
    document.querySelector('.backing_vocals')?.classList.toggle('hidden', !hasBackingVocals);

    // Reset status text on new song load
    const status = document.getElementById('vocalSplitStatus');
    if (status) status.textContent = '';
  }

  // ── Solfège seek ─────────────────────────────────────────────────────────
  document.addEventListener('solfa:seek', (e) => studio.seek(e.detail.time));
  document.addEventListener('lyrics:seek', (e) => studio.seek(e.detail.time));

  // ── Solfa panel collapse ─────────────────────────────────────────────────
  const bindCollapse = (buttonId, bodyId, panelId) => {
    const button = document.getElementById(buttonId);
    const body = document.getElementById(bodyId);
    const panel = document.getElementById(panelId);
    button?.addEventListener('click', () => {
      const expanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', String(!expanded));
      body?.toggleAttribute('hidden', expanded);
      panel?.classList.toggle('is-collapsed', expanded);
      const chevron = button.querySelector('polyline');
      chevron?.setAttribute('points', expanded ? '6 9 12 15 18 9' : '18 15 12 9 6 15');
    });
  };
  bindCollapse('solfaCollapseBtn', 'solfaBody', 'solfaPanel');

  // ── Lyrics panel collapse ─────────────────────────────────────────────────
  bindCollapse('lyricsCollapseBtn', 'lyricsBody', 'lyricsPanel');

  // ── VU meter panel toggle ─────────────────────────────────────────────────
  const vuToggle = document.getElementById('vuToggleBtn');
  const vuPanel  = document.getElementById('vuMeterPanel');
  vuToggle?.addEventListener('click', () => {
    const on = State.vuVisible = !State.vuVisible;
    vuToggle.setAttribute('aria-pressed', on);
    vuToggle.classList.toggle('active', on);
    vuPanel?.classList.toggle('hidden', !on);
  });

  const vuCollapseBtn = document.getElementById('vuMeterCollapseBtn');
  const vuBody        = document.getElementById('vuMeterBody');
  vuCollapseBtn?.addEventListener('click', () => {
    const expanded = vuCollapseBtn.getAttribute('aria-expanded') === 'true';
    vuCollapseBtn.setAttribute('aria-expanded', !expanded);
    if (vuBody) vuBody.style.display = expanded ? 'none' : '';
  });

  // ── Beat grid toolbar ────────────────────────────────────────────────────
  beatGrid.init();

  // ── Sections ─────────────────────────────────────────────────────────────
  sections.init();

  // ── Vocal split ──────────────────────────────────────────────────────────
  document.getElementById('vocalSplitBtn')?.addEventListener('click', async () => {
    const songId = State.songId;
    if (!songId) return;
    const btn    = document.getElementById('vocalSplitBtn');
    const status = document.getElementById('vocalSplitStatus');
    if (btn) { btn.disabled = true; btn.textContent = 'Splitting…'; }
    if (status) status.textContent = '';
    try {
      const result = await API.triggerVocalSplit(songId);
      if (status) status.textContent = `✓ ${result.new_stems?.join(' + ') || 'Done'}`;
      // Reload the song so new stems appear in the mixer
      await studio.loadSong(songId);
    } catch (err) {
      if (status) status.textContent = `Failed: ${err.message}`;
      console.error('[vocal-split]', err);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Split Lead / Backing Vocals';
      }
    }
  });

  // ── Panel toggles (Analysis / Sections) ──────────────────────────────────
  document.querySelectorAll('.daw-panel-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const panel   = btn.dataset.panel;
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', !pressed);
      const target = panel === 'analysis'
        ? document.getElementById('transport')
        : document.querySelector('.daw-section-ribbon');
      if (target) target.style.display = pressed ? 'none' : '';
    });
  });

  // ── Sidebar collapse ─────────────────────────────────────────────────────
  const collapseBtn = document.getElementById('sidebarCollapseBtn');
  const sidebar     = document.getElementById('catalogPanel');
  collapseBtn?.addEventListener('click', () => {
    const expanded = collapseBtn.getAttribute('aria-expanded') === 'true';
    collapseBtn.setAttribute('aria-expanded', !expanded);
    sidebar?.classList.toggle('collapsed', expanded);
  });

  // ── Import button ─────────────────────────────────────────────────────────
  document.getElementById('importBtn')?.addEventListener('click', () =>
    document.getElementById('fileInput')?.click()
  );
  document.getElementById('uploadFileBtn')?.addEventListener('click', () =>
    document.getElementById('fileInput')?.click()
  );

  // ── Export panel ─────────────────────────────────────────────────────────
  const exportBtn   = document.getElementById('t-export-btn');
  const exportPanel = document.getElementById('t-export-panel');
  exportBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = exportPanel?.classList.toggle('hidden') === false;
    exportBtn.setAttribute('aria-expanded', open);
  });
  document.addEventListener('click', () => exportPanel?.classList.add('hidden'));

  document.getElementById('t-export-mix')?.addEventListener('click', () => {
    studio.exportMix(); exportPanel?.classList.add('hidden');
  });
  document.getElementById('t-export-stems')?.addEventListener('click', () => {
    studio.exportStems(); exportPanel?.classList.add('hidden');
  });

  // Per-stem export buttons wired dynamically when stems load (see _updateExportPerStemPanel)

  // ── Metro volume popover ─────────────────────────────────────────────────
  const metroVolBtn   = document.getElementById('t-metro-vol-btn');
  const metroVolPanel = document.getElementById('t-metro-vol-panel');
  metroVolBtn?.addEventListener('click', (e) => {
    e.stopPropagation(); metroVolPanel?.classList.toggle('hidden');
  });
  document.addEventListener('click', () => metroVolPanel?.classList.add('hidden'));

  // ── Boot modules ─────────────────────────────────────────────────────────
  await catalog.load();
  transport.init();
  importer.init();
  initExtractPanel({ api: API, state: State });
  settings.init();

  console.log('[mwtn] ready');
}

// ── Per-stem export panel ─────────────────────────────────────────────────────

function _updateExportPerStemPanel() {
  const container = document.getElementById('export-per-stem-list');
  if (!container) return;
  const manifest = window._mwtn?.State?.manifest;
  const State    = window._mwtn?.State;
  const studio   = window._mwtn?._studio;
  if (!manifest?.stems?.length) { container.innerHTML = ''; return; }

  container.innerHTML = '';
  manifest.stems.forEach(name => {
    const color = ({
      vocals:'#e85f6f', drums:'#e89048', bass:'#e8b848',
      guitar:'#88d878', piano:'#b88fe0', other:'#88a8c8',
    })[name] || '#888';

    const row = document.createElement('div');
    row.className = 'export-stem-row';
    row.innerHTML = `
      <span class="export-stem-dot" style="background:${color}"></span>
      <span class="export-stem-name">${name.replace('_',' ')}</span>
      <input type="range" class="export-stem-gain" min="0" max="1.5" step="0.01"
             value="${State?.mixer?.[name]?.volume ?? 1}" style="--track-fill:${color}"
             aria-label="${name} export gain">
      <span class="export-stem-pct">100%</span>
      <button class="export-stem-dl" data-stem="${name}" type="button" title="Download ${name}">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
      </button>
    `;

    const gainSlider = row.querySelector('.export-stem-gain');
    const pctLabel   = row.querySelector('.export-stem-pct');
    gainSlider.addEventListener('input', () => {
      pctLabel.textContent = `${Math.round(parseFloat(gainSlider.value) * 100)}%`;
    });

    row.querySelector('.export-stem-dl').addEventListener('click', () => {
      if (!State?.songId) return;
      const gain = parseFloat(gainSlider.value);
      const ext  = State.exportFormat || 'wav';
      const loopOpts = (State.exportLoopOnly && State.loopEnabled && State.loopEnd > State.loopStart)
        ? { start: State.loopStart, end: State.loopEnd } : {};
      const url = window._mwtn?.API?.singleStemUrl(State.songId, name, { gain, ext, ...loopOpts });
      if (url) window._mwtn?.API?.triggerDownload(url, `${State.songId}_${name}.${ext}`);
    });

    container.appendChild(row);
  });
}

// Expose _studio for the per-stem panel helper
boot().then(() => {}).catch(err => {
  console.error('[mwtn] boot failed:', err);
  const errEl = document.getElementById('error');
  if (errEl) { errEl.textContent = `Failed to start: ${err.message}`; errEl.classList.remove('hidden'); }
});

