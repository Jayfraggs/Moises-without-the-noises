/**
 * lyrics.js — Synced Lyrics Panel.
 *
 * Mirrors the architecture of solfa.js exactly so the two panels
 * behave consistently:
 *
 *   1. When a song loads, call LyricsPanel.loadSong(songId).
 *      - Tries GET /api/songs/{id}/lyrics.
 *      - If 404, shows a "No lyrics" empty state.
 *      - On success, renders one pill per word.
 *   2. Studio calls LyricsPanel.tick(currentTime) on every animation frame.
 *      The active word (whose [start, end) window covers currentTime) is
 *      highlighted and scrolled into view.
 *   3. LyricsPanel.clear() resets state when a new song is loaded.
 *
 * Data shape from GET /api/songs/{id}/lyrics:
 *   {
 *     language: "en",
 *     text: "full transcript string",
 *     words: [
 *       { word: "Hello", start: 0.42, end: 0.88 },
 *       ...
 *     ]
 *   }
 */

function el(id) { return document.getElementById(id); }

export class LyricsPanel {
  constructor({ API }) {
    this.API      = API;
    this._songId  = null;
    this._words   = [];    // sorted array of { word, start, end }
    this._current = -1;
    this._loaded  = false;

    this._panel   = el('lyricsPanel');
    this._grid    = el('lyricsGrid');
    this._langEl  = el('lyricsLangBadge');
    this._emptyEl = el('lyricsEmpty');
    this._phrase  = el('lyricsPhrase');
    this._spinner = el('lyricsSpinner');
    this._nowEl   = el('lyricsNow');
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  async loadSong(songId) {
    this._songId  = songId;
    this._words   = [];
    this._current = -1;
    this._loaded  = false;
    this._showState('loading');

    try {
      const data = await this.API.getLyrics(songId);
      if (!data) {
        this._showState('empty');
        return;
      }
      this._ingest(data);
    } catch (err) {
      this._showState('empty');
    }
  }

  /** Called by Studio's rAF loop on every animation frame. */
  tick(currentTime) {
    if (!this._loaded || !this._words.length) return;
    const idx = this._findWord(currentTime);
    if (idx === this._current) return;
    this._current = idx;
    this._highlight(idx);
  }

  clear() {
    this._songId  = null;
    this._words   = [];
    this._current = -1;
    this._loaded  = false;
    if (this._grid)   this._grid.innerHTML = '';
    if (this._nowEl)  { this._nowEl.textContent = ''; this._nowEl.style.display = 'none'; }
    if (this._langEl) this._langEl.textContent = '';
    this._showState('idle');
  }

  // ── Private ────────────────────────────────────────────────────────────────

  _ingest(data) {
    this._words  = (data.words || []).slice().sort((a, b) => a.start - b.start);
    this._loaded = true;

    if (this._langEl) {
      const lang = data.language || '';
      this._langEl.textContent = lang;
      this._langEl.style.display = lang ? '' : 'none';
    }

    this._renderGrid();
    this._showState('ready');
  }

  _renderGrid() {
    if (!this._grid) return;
    this._grid.innerHTML = '';

    this._words.forEach((w, i) => {
      const pill = document.createElement('span');
      pill.className = 'lyrics-word';
      pill.dataset.idx = i;
      pill.textContent = w.word;
      pill.title = `${w.start.toFixed(2)}s – ${w.end.toFixed(2)}s`;

      pill.addEventListener('click', () => {
        document.dispatchEvent(new CustomEvent('lyrics:seek', { detail: { time: w.start } }));
      });

      this._grid.appendChild(pill);

      // Insert a line-break hint between sentences (punctuation at word end)
      if (/[.!?]$/.test(w.word.trim())) {
        const br = document.createElement('span');
        br.className = 'lyrics-break';
        this._grid.appendChild(br);
      }
    });
  }

  /**
   * Binary search: return index of the word active at time t, or -1.
   */
  _findWord(t) {
    const ws = this._words;
    if (!ws.length) return -1;
    let lo = 0, hi = ws.length - 1, best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const w   = ws[mid];
      if (t >= w.start && t < w.end) return mid;
      if (w.start <= t) { best = mid; lo = mid + 1; }
      else              hi = mid - 1;
    }
    if (best >= 0) {
      const w = ws[best];
      if (t >= w.start && t < w.end) return best;
    }
    return -1;
  }

  _highlight(idx) {
    // Clear previous
    this._grid?.querySelectorAll('.lyrics-word.active').forEach(p => p.classList.remove('active'));

    if (idx < 0) {
      if (this._nowEl) this._nowEl.style.display = 'none';
      return;
    }

    const pill = this._grid?.querySelector(`.lyrics-word[data-idx="${idx}"]`);
    if (pill) {
      pill.classList.add('active');
      pill.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    const w = this._words[idx];
    if (this._nowEl && w) {
      this._nowEl.style.display   = '';
      this._nowEl.textContent     = w.word;
    }
  }

  _showState(state) {
    const show = (id, on) => { const e = el(id); if (e) e.style.display = on ? '' : 'none'; };
    show('lyricsEmpty',   state === 'empty' || state === 'idle');
    show('lyricsSpinner', state === 'loading');

    const phrases = {
      idle:    '',
      loading: 'Loading lyrics…',
      empty:   'No lyrics available for this song.',
      ready:   '',
    };
    if (this._phrase) this._phrase.textContent = phrases[state] ?? '';
  }
}
