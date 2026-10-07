import { API } from '../api.js';

const SETTINGS_KEY = 'mwtn_extract_settings';
const defaults = { demucs_model:'htdemucs_6s', proc_path:'colab', enable_whisper:true, whisper_model:'small', whisper_language:'auto', enable_alignment:true, enable_notes:true, note_confidence:'0.6', note_min_dur:'0.1', enable_chords:true, enable_solfa:true, solfa_system:'movable_do', solfa_minor:'la_based', solfa_colours:true, quantize_grid:'16', enable_beaming:true, enable_confidence:true, confidence_threshold:'0.15', export_format:'wav', export_include_click:false, job_max_retries:'2', stale_threshold:'600' };
const select = (options) => `<select name="">${options.map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select>`;
const control = (name, label, markup) => `<label class="extract-control"><span>${label}</span>${markup.replace('name=""', `name="${name}"`)}</label>`;
const toggle = (name, label) => `<label class="extract-toggle-row"><input type="checkbox" id="${name}" name="${name}"><span>${label}</span></label>`;
const section = (title, body) => `<div class="extract-section"><h3>${title}</h3>${body}</div>`;
const pane = (name, body, active = false) => `<section class="extract-pane" data-pane="${name}"${active ? '' : ' hidden'}>${body}</section>`;
function radio(name, value, label, description, checked = false) { return `<label class="extract-radio"><input type="radio" name="${name}" value="${value}"${checked ? ' checked' : ''}><span>${label}</span><small>${description}</small></label>`; }

function template() {
  const separation = section('Stem Model', '<div class="extract-radio-group" id="extract-model-select"><p class="extract-hint">Loading installed model options…</p></div>') + section('Stems to Separate', '<div class="extract-check-group" id="extract-stem-select"></div><p class="extract-hint">Only stems produced by the selected model are available. Deselecting a stem skips writing its WAV file.</p>') + section('Processing Path', `<div class="extract-radio-group">${radio('proc_path','colab','Google Colab (GPU) <b class="extract-badge">Planned</b>','Plan 12 queue integration is not enabled yet.',true)}${radio('proc_path','local','Local CPU','Slow (30–90 min). Runs on this machine.')}</div>`);
  const transcription = section('Lyric Transcription (Whisper)', toggle('enable_whisper','Enable lyric transcription') + `<div class="extract-sub-settings">${control('whisper_model','Whisper model',select([['tiny','tiny — fastest'],['base','base'],['small','small — recommended'],['medium','medium — WiFi only']]))}${control('whisper_language','Language',select([['auto','Auto-detect'],['en','English'],['es','Spanish'],['pt','Portuguese'],['fr','French'],['it','Italian'],['yo','Yoruba'],['ha','Hausa'],['ig','Igbo'],['sw','Swahili']]))}${toggle('enable_alignment','Align lyrics to notes')}</div>`) + section('Note Extraction (pYIN)', toggle('enable_notes','Extract notes from pitched stems') + `<div class="extract-sub-settings"><p class="extract-hint">Pitched stems: vocals, bass, guitar, piano.</p>${control('note_confidence','Confidence threshold',select([['0.5','Lenient'],['0.6','Standard — recommended'],['0.75','Strict']]))}${control('note_min_dur','Min note duration',select([['0.05','50 ms'],['0.1','100 ms — recommended'],['0.2','200 ms']]))}</div>`) + section('Chord Detection', toggle('enable_chords','Detect chords from harmonic content'));
  const score = section('Solfege', toggle('enable_solfa','Generate solfege annotations') + `<div class="extract-sub-settings">${control('solfa_system','System',select([['movable_do','Movable Do — recommended'],['fixed_do','Fixed Do']]))}${control('solfa_minor','Minor key convention',select([['la_based','La-based minor'],['do_based','Do-based minor']]))}${toggle('solfa_colours','Show syllable colours')}</div>`) + section('Rhythm Quantization', control('quantize_grid','Smallest note value',select([['8','Eighth note'],['16','Sixteenth note — recommended'],['32','Thirty-second note']])) + toggle('enable_beaming','Auto-beam eighth and sixteenth notes')) + section('Confidence Review', toggle('enable_confidence','Run confidence scoring') + `<div class="extract-sub-settings">${control('confidence_threshold','Flag threshold',select([['0.10','10% flagged'],['0.15','15% flagged — recommended'],['0.25','25% flagged']]))}</div>`);
  const exports = section('Score Export', `<div class="extract-export-grid">${[['midi','MIDI','Multi-track .mid file.'],['musicxml','MusicXML','Standard notation file.'],['click','Click Track','Mono WAV click track.']].map(([type,title,description]) => `<div class="extract-export-card"><strong>${title}</strong><small>${description}</small><button class="extract-download-btn" data-export="${type}" type="button">Download</button></div>`).join('')}</div><p class="extract-hint">Score exports are planned for the transcription backend.</p>`) + section('Stem Audio Export', `<div class="extract-export-row">${control('export_format','Format',select([['wav','WAV'],['mp3','MP3'],['flac','FLAC']]))}<button id="export-mix-btn" type="button">Export Mix</button><button id="export-stems-btn" type="button">Export All Stems</button></div>${toggle('export_include_click','Include click track in mix export')}`);
  const advanced = section('Colab Automation', control('papermill_notebook','Notebook path','<input type="text" name="" value="colab/mwtn_notebook.ipynb">') + control('papermill_output','Output path','<input type="text" name="">') + toggle('papermill_auto','Auto-run notebook when queued') + '<p class="extract-hint">Requires Papermill. Plan 12 queue integration is pending.</p>') + section('Job Queue', control('job_max_retries','Max retries',select([['1','1'],['2','2 — recommended'],['3','3']])) + control('stale_threshold','Stale job timeout',select([['300','5 minutes'],['600','10 minutes — recommended'],['1200','20 minutes']])));
  const tabs = ['separation','transcription','score','export','advanced'];
  return `<div class="extract-panel-overlay" id="extract-overlay" hidden><div class="extract-panel" role="dialog" aria-modal="true" aria-labelledby="extract-title"><header class="extract-header"><h2 id="extract-title">Extract &amp; Analyse</h2><button id="extract-close" type="button" aria-label="Close">×</button></header><nav class="extract-tabs" role="tablist">${tabs.map((tab, index) => `<button class="extract-tab${index === 0 ? ' active' : ''}" data-tab="${tab}" role="tab" aria-selected="${index === 0}">${tab[0].toUpperCase() + tab.slice(1)}</button>`).join('')}</nav><div class="extract-body">${pane('separation',separation,true)}${pane('transcription',transcription)}${pane('score',score)}${pane('export',exports)}${pane('advanced',advanced)}</div><footer class="extract-footer"><span class="extract-status" id="extract-status" role="status"></span><button id="extract-run-btn" class="extract-run-btn" type="button">Run Selected</button></footer></div></div>`;
}

export class ExtractPanel {
  constructor({ api = API, state = window._mwtn?.State } = {}) { this.api = api; this.state = state; this.settings = { ...defaults, ...this._read() }; this.models = {}; }
  init() { if (!document.getElementById('extract-overlay')) document.body.insertAdjacentHTML('beforeend', template()); this.overlay = document.getElementById('extract-overlay'); this._bind(); this._apply(); this._loadModels(); document.getElementById('extractMenuBtn')?.addEventListener('click', () => this.open()); document.addEventListener('extract:open', () => this.open()); return this; }
  _read() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}'); } catch { return {}; } }
  _save() { localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.settings)); }
  async _loadModels() {
    const target = this.overlay.querySelector('#extract-model-select');
    try {
      const config = await this.api.getConfig();
      this.models = config.separation_models || {};
      if (!this.models[this.settings.demucs_model]) this.settings.demucs_model = config.default_model || Object.keys(this.models)[0];
      this._renderModels();
    } catch (error) {
      if (target) target.innerHTML = '<p class="extract-hint">Model options could not be loaded. Check that the local backend is running.</p>';
      this._status(`Could not load separation models: ${error.message}`);
    }
  }
  _renderModels() {
    const target = this.overlay.querySelector('#extract-model-select');
    if (!target) return;
    target.replaceChildren();
    Object.entries(this.models).forEach(([name, model]) => {
      const label = document.createElement('label'); label.className = 'extract-radio';
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'demucs_model'; input.value = name; input.checked = name === this.settings.demucs_model;
      input.addEventListener('change', () => { this.settings.demucs_model = name; this._save(); this._renderStems(); });
      const title = document.createElement('span'); title.textContent = `${name} (${model.stems.length} stems)`;
      if (name === 'htdemucs_6s') title.insertAdjacentHTML('beforeend', ' <b class="extract-badge">Recommended</b>');
      const description = document.createElement('small'); description.textContent = model.description;
      label.append(input, title, description); target.append(label);
    });
    this._renderStems();
  }
  _renderStems() {
    const target = this.overlay.querySelector('#extract-stem-select');
    const model = this.models[this.settings.demucs_model];
    if (!target || !model) return;
    const current = [...this.overlay.querySelectorAll('[name="stem"]:checked')].map((input) => input.value);
    const previous = new Set(current.length ? current : (this.settings.selected_stems || []));
    target.replaceChildren();
    model.stems.forEach((stem) => {
      const label = document.createElement('label');
      const input = document.createElement('input'); input.type = 'checkbox'; input.name = 'stem'; input.value = stem; input.checked = previous.size ? previous.has(stem) : true;
      input.addEventListener('change', () => { this.settings.selected_stems = [...target.querySelectorAll('input:checked')].map((item) => item.value); this._save(); });
      label.append(input, ` ${stem.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())}`); target.append(label);
    });
  }
  _apply() { this.overlay.querySelectorAll('[name]').forEach((element) => { if (element.name === 'stem') return; const value = this.settings[element.name]; if (value === undefined) return; if (element.type === 'radio') element.checked = value === element.value; else if (element.type === 'checkbox') element.checked = Boolean(value); else element.value = value; }); this._refreshExports(); }
  _bind() { this.overlay.addEventListener('change', (event) => { const element = event.target; if (element.name === 'stem') return; if (element.name) this.settings[element.name] = element.type === 'checkbox' ? element.checked : element.value; this._save(); if (element.name === 'solfa_colours') document.dispatchEvent(new CustomEvent('solfa:colours-changed')); this._refreshExports(); }); this.overlay.querySelectorAll('.extract-tab').forEach((tab) => tab.addEventListener('click', () => { this.overlay.querySelectorAll('.extract-tab').forEach((item) => { const active = item === tab; item.classList.toggle('active', active); item.setAttribute('aria-selected', active); }); this.overlay.querySelectorAll('.extract-pane').forEach((item) => { item.hidden = item.dataset.pane !== tab.dataset.tab; }); })); document.getElementById('extract-close').addEventListener('click', () => this.close()); this.overlay.addEventListener('click', (event) => { if (event.target === this.overlay) this.close(); }); document.getElementById('extract-run-btn').addEventListener('click', () => this.run()); this.overlay.querySelectorAll('[data-export]').forEach((button) => button.addEventListener('click', () => this.export(button.dataset.export))); document.getElementById('export-mix-btn').addEventListener('click', () => window._mwtn?._studio?.exportMix()); document.getElementById('export-stems-btn').addEventListener('click', () => window._mwtn?._studio?.exportStems()); }
  _refreshExports() { const manifest = this.state?.manifest || {}; this.overlay.querySelectorAll('[data-export]').forEach((button) => { const ready = button.dataset.export === 'click' ? manifest.has_beats : Boolean(manifest.notes_available?.length); button.disabled = !ready; button.dataset.disabledReason = ready ? '' : (button.dataset.export === 'click' ? 'Run beat detection first' : 'Run note extraction first'); }); }
  _payload() { return { ...this.settings, stems: [...this.overlay.querySelectorAll('[name="stem"]:checked')].map((element) => element.value), demucs_model: this.overlay.querySelector('[name="demucs_model"]:checked')?.value, proc_path: this.overlay.querySelector('[name="proc_path"]:checked')?.value }; }
  run() { const payload = this._payload(); if (payload.proc_path === 'colab') { this._status('Colab queue is planned for Plan 12. Select Local CPU to continue now.'); return; } this.close(); document.getElementById('fileInput')?.click(); }
  export(type) { if (!this.state?.manifest) { this._status('Load a song before exporting.'); return; } this._status(`${type.toUpperCase()} export is planned for the transcription backend.`); }
  _status(message) { const status = document.getElementById('extract-status'); if (status) status.textContent = message; }
  open() { this._apply(); this.overlay.hidden = false; }
  close() { this.overlay.hidden = true; }
}

export function initExtractPanel(options) { return new ExtractPanel(options).init(); }
