/**
 * extract.js — Extraction Settings modal.
 *
 * Two action paths:
 *   A) Copy Colab Settings — builds a string to paste into Colab Cell 3.
 *   B) Run Locally — triggers POST /api/import with the staged audio file
 *      using the selected model; hands off to the Import module for polling.
 *
 * Model data is fetched once from GET /api/config and cached.
 */
export class Extract {
  constructor({ API }) {
    this.API      = API;
    this._config  = null;
    this._model   = null;
    this._stems   = new Set();
    this._lyrics  = true;
    this._solfa   = false;
  }

  async init() {
    const btn   = document.getElementById('extractMenuBtn');
    const modal = document.getElementById('extractModal');
    const close = document.getElementById('extractModalClose');
    const copy  = document.getElementById('extractCopyBtn');
    const runLocal = document.getElementById('extractRunLocalBtn');

    btn?.addEventListener('click', async () => {
      await this._ensureConfig();
      this._renderModal();
      modal?.classList.remove('hidden');
    });

    close?.addEventListener('click', () => modal?.classList.add('hidden'));

    modal?.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });

    copy?.addEventListener('click', () => this._copySettings(copy));

    runLocal?.addEventListener('click', () => {
      modal?.classList.add('hidden');
      // Trigger the file picker so the user picks the audio file
      // The selected model is read from extractModelSelect in import.js
      document.getElementById('fileInput')?.click();
    });

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

    const fresh = select.cloneNode(true);
    select.parentNode.replaceChild(fresh, select);
    fresh.addEventListener('change', () => {
      this._model = fresh.value;
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

    const descEl = document.createElement('p');
    descEl.className = 'extract-model-desc';
    descEl.textContent = desc;
    grid.appendChild(descEl);

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
      el.textContent = `⚠ ~${mb} MB download on first run for this model`;
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
