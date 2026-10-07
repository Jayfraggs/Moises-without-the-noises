import { API } from './api.js';

const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const MODES = ['major', 'minor', 'dorian', 'mixolydian', 'phrygian'];
const QUALITY = { major: '', minor: 'm', diminished: 'dim', augmented: 'aug', dominant7: '7', major7: 'maj7', minor7: 'm7' };

export class HarmonicPanel {
  constructor({ State, API: api = API }) { this.State = State; this.API = api; this.el = document.getElementById('harmonicPanel'); this.time = 0; this.songId = null; this.collapsed = false; }
  init() {
    if (!this.el) return;
    this.el.addEventListener('click', (event) => this.onClick(event));
    this.el.addEventListener('change', (event) => this.onChange(event));
    this.render();
  }
  async loadSong(songId) {
    this.songId = songId; this.time = 0; this.render({ loading: true });
    try {
      const [keyMap, chords] = await Promise.all([this.API.getKeyMap(songId), this.API.getChords(songId)]);
      this.keyMap = keyMap?.key_map || []; this.chords = Array.isArray(chords) ? chords : (chords?.chords || []); this.error = null;
    } catch (error) { this.keyMap = []; this.chords = []; this.error = error.message; }
    this.render();
  }
  tick(time) { this.time = Number(time) || 0; if (this.el) this.render(); }
  activeKey() { return [...(this.keyMap || [])].reverse().find((item) => item.start_s <= this.time && (item.end_s == null || this.time < item.end_s)) || this.keyMap?.[0]; }
  render(options = {}) {
    if (!this.el) return;
    if (options.loading) { this.el.innerHTML = '<div class="harmonic-loading">Loading harmonic analysis…</div>'; return; }
    const key = this.activeKey(); const duration = Math.max(Number(this.State.duration) || 1, 0.001);
    const blocks = (this.chords || []).map((chord) => {
      const width = Math.max(0.5, ((Number(chord.end_time) - Number(chord.start_time)) / duration) * 100);
      const active = chord.start_time <= this.time && (chord.end_time == null || this.time < chord.end_time);
      const qualityLabel = QUALITY[chord.quality] ?? (chord.quality || '');
      return `<button class="chord-block${active ? ' chord-block--active' : ''}" data-chord-id="${escapeAttr(chord.event_id || '')}" style="width:${width}%">${escapeHtml(chord.root || '?')}${escapeHtml(qualityLabel)}</button>`;
    }).join('');
    this.el.classList.toggle('is-collapsed', this.collapsed);
    this.el.innerHTML = `<header class="harmonic-panel__header"><h2>Harmonic Analysis</h2><div class="harmonic-panel__actions"><button type="button" data-action="analyze">Analyze</button><button type="button" class="harmonic-collapse-btn" data-action="collapse" aria-expanded="${!this.collapsed}" aria-controls="harmonicBody" title="${this.collapsed ? 'Expand' : 'Collapse'}">${this.collapsed ? '▾' : '▴'}</button></div></header><div id="harmonicBody"${this.collapsed ? ' hidden' : ''}>${this.error ? `<p class="harmonic-error" role="alert">${escapeHtml(this.error)}</p>` : ''}<div class="key-display"><span class="key-display__label">Key</span><strong>${key ? `${escapeHtml(key.tonic)} ${escapeHtml(key.mode)}` : 'No key analysis'}</strong><button type="button" data-action="override-key">Override</button>${key ? `<span class="key-display__confidence">${Math.round((Number(key.confidence) || 0) * 100)}%</span>` : ''}</div><div class="harmonic-panel__section"><h3>Chord Chart</h3>${blocks ? `<div class="chord-chart__timeline">${blocks}</div>` : '<div class="harmonic-empty">No chord analysis yet.</div>'}</div></div>`;
  }
  async onClick(event) {
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'collapse') { this.collapsed = !this.collapsed; this.render(); return; }
    if (action === 'analyze' && this.songId) {
      try { await this.API.detectChords(this.songId); await this.loadSong(this.songId); }
      catch (error) { this.error = error.message; this.render(); }
    }
    if (action === 'override-key') this.showKeyEditor();
  }
  onChange(event) { if (event.target.dataset.keyField) this[`_${event.target.dataset.keyField}`] = event.target.value; }
  showKeyEditor() { if (!this.el) return; const key = this.activeKey() || { tonic: 'C', mode: 'major' }; this.el.querySelector('.key-display').insertAdjacentHTML('beforeend', `<div class="key-override"><select data-key-field="tonic">${NOTES.map((n) => `<option${n === key.tonic ? ' selected' : ''}>${n}</option>`).join('')}</select><select data-key-field="mode">${MODES.map((m) => `<option${m === key.mode ? ' selected' : ''}>${m}</option>`).join('')}</select><button type="button" data-action="apply-key">Apply</button></div>`); this.el.querySelector('[data-action="apply-key"]').addEventListener('click', async () => { await this.API.patchKey(this.songId, { tonic: this._tonic || key.tonic, mode: this._mode || key.mode, start_s: this.time, end_s: null }); await this.loadSong(this.songId); }); }
}
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])); }
function escapeAttr(value) { return escapeHtml(value); }
