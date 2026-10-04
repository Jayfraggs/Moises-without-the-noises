/**
 * extract.js — Extract configuration modal.
 *
 * Replaces the topbar stem chip strip with a button that opens a modal where
 * the user picks their separation model, stem subset, and extra options
 * (lyrics, bass solfège). A "Copy Colab settings" button produces a string
 * the user pastes into Colab Cell 3 — no server call is made here.
 *
 * Model data is fetched once from GET /api/config and cached.
 */
export class Extract {
  constructor({ API }) {
    this.API      = API;
    this._config  = null;   // cached /api/config response
    this._model   = null;   // currently selected model key
    this._stems   = new Set();
    this._lyrics  = true;
    this._solfa   = false;
  }

  async init() {
    const btn   = document.getElementById('extractMenuBtn');
    const modal = document.getElementById('extractModal');
    const close = document.getElementById('extractModalClose');
    const copy  = document.getElementById('extractCopyBtn');

    btn?.addEventListener('click', async () => {
      await this._ensureConfig();
      this._renderModal();
      modal?.classList.remove('hidden');
    });

    close?.addEventListener('click', () => modal?.classList.add('hidden'));

    // Close on backdrop click
    modal?.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });

    copy?.addEventListener('click', () => this._copySettings(copy));

    // Lyrics / solfa toggles
    document.getElementById('extractLyrics')?.addEventListener('change', (e) => {
      this._lyrics = e.target.checked;
    });
    document.getElementById('extractSolfa')?.addEventListener('change', (e) => {
      this._solfa = e.target.checked;
    });
  }

  async _ensureConfig() {
    if (this._config) return;
    try {
      this._config = await this.API.getConfig();
      this._model  = this._config.default_model;
      // Seed stems from default model
      const modelStems = this._config.separation_models[this._model]?.stems || [];
      this._stems = new Set(modelStems);
    } catch (err) {
      console.warn('[extract] could not fetch /api/config:', err);
      this._config = { separation_models: {}, default_model: 'htdemucs_6s' };
    }
  }

  _renderModal() {
    this._renderModelSelect();
    this._renderStemGrid();
    this._renderDataCost();
  }

  _renderModelSelect() {
    const select = document.getElementById('extractModelSelect');
    if (!select || !this._config) return;

    select.innerHTML = '';
    const models = this._config.separation_models || {};
    Object.entries(models).forEach(([key, info]) => {
      const opt = document.createElement('option');
      opt.value = key;
      const stemCount = (info.stems || []).length;
      opt.textContent = `${key}  —  ${stemCount} stems`;
      if (key === this._model) opt.selected = true;
      select.appendChild(opt);
    });

    // Remove old listener by replacing node
    const fresh = select.cloneNode(true);
    select.parentNode.replaceChild(fresh, select);
    fresh.addEventListener('change', () => {
      this._model = fresh.value;
      // Reset stem selection to match the new model
      const modelStems = this._config.separation_models[this._model]?.stems || [];
      this._stems = new Set(modelStems);
      this._renderStemGrid();
      this._renderDataCost();
    });
  }

  _renderStemGrid() {
    const grid = document.getElementById('extractStemGrid');
    if (!grid || !this._config) return;

    const modelInfo = this._config.separation_models[this._model] || {};
    const available = modelInfo.stems || [];
    const desc      = modelInfo.description || '';

    grid.innerHTML = '';

    // Model description line
    const descEl = document.createElement('p');
    descEl.className = 'extract-model-desc';
    descEl.textContent = desc;
    grid.appendChild(descEl);

    // Stem checkboxes
    const checkWrap = document.createElement('div');
    checkWrap.className = 'extract-stem-checks';
    available.forEach(stem => {
      const label = document.createElement('label');
      label.className = 'extract-stem-check-label';
      const cb = document.createElement('input');
      cb.type    = 'checkbox';
      cb.value   = stem;
      cb.checked = this._stems.has(stem);
      cb.addEventListener('change', () => {
        if (cb.checked) this._stems.add(stem);
        else            this._stems.delete(stem);
      });
      const dot = document.createElement('span');
      dot.className = `extract-stem-dot stem-dot-${stem}`;
      const name = document.createElement('span');
      name.textContent = stem.replace('_', ' ');
      label.appendChild(cb);
      label.appendChild(dot);
      label.appendChild(name);
      checkWrap.appendChild(label);
    });
    grid.appendChild(checkWrap);
  }

  _renderDataCost() {
    const el = document.getElementById('extractDataCost');
    if (!el || !this._config) return;
    const modelInfo = this._config.separation_models[this._model] || {};
    const mb = modelInfo.data_cost_mb;
    if (mb != null) {
      el.textContent = `⚠ ~${mb} MB Colab download on first run for this model`;
      el.style.display = '';
    } else {
      el.style.display = 'none';
    }
  }

  _copySettings(btn) {
    const stemList = [...this._stems].join(',');
    const text = [
      `MODEL=${this._model || 'htdemucs_6s'}`,
      `STEMS=${stemList}`,
      `LYRICS=${this._lyrics ? 'True' : 'False'}`,
      `SOLFA=${this._solfa ? 'True' : 'False'}`,
    ].join('\n');

    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = orig; }, 1800);
    }).catch(() => {
      // Fallback for environments without clipboard API
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity  = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = orig; }, 1800);
    });
  }
}
