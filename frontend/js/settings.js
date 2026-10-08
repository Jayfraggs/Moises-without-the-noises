/**
 * settings.js — Settings dialog: Drive path, folder name, Colab link, scan.
 */
export class Settings {
  constructor({ State, API, catalog }) {
    this.State   = State;
    this.API     = API;
    this.catalog = catalog;

    this._dialog   = document.getElementById('settingsDialog');
    this._openBtn  = document.getElementById('settingsBtn');
    this._closeBtn = document.getElementById('settingsClose');
    this._pathEl   = document.getElementById('settingsDrivePath');
    this._folderEl = document.getElementById('settingsFolderName');
    this._scanBtn  = document.getElementById('settingsScanBtn');
    this._saveBtn  = document.getElementById('settingsSaveBtn');
    this._colabLink= document.getElementById('settingsOpenColab');
  }

  init() {
    // Populate saved values
    if (this._pathEl)   this._pathEl.value   = this.State.drivePath;
    if (this._folderEl) this._folderEl.value = this.State.folderName;

    this._openBtn?.addEventListener('click', () => {
      this._dialog?.classList.remove('hidden');
    });
    this._closeBtn?.addEventListener('click', () => {
      this._dialog?.classList.add('hidden');
    });
    this._dialog?.addEventListener('click', (e) => {
      if (e.target === this._dialog) this._dialog.classList.add('hidden');
    });

    this._saveBtn?.addEventListener('click', () => {
      this.State.drivePath  = this._pathEl?.value.trim()  || '';
      this.State.folderName = this._folderEl?.value.trim() || 'mwtn-outputs';
      this.State.saveSettings();
      this._dialog?.classList.add('hidden');
    });

    this._scanBtn?.addEventListener('click', () => this._runScan());

    this._colabLink?.addEventListener('click', (e) => {
      e.preventDefault();
      const url = 'https://colab.research.google.com';
      if (window.electronAPI?.openExternal) window.electronAPI.openExternal(url);
      else window.open(url, '_blank', 'noopener,noreferrer');
    });
  }

  async _runScan() {
    const path       = this._pathEl?.value.trim()   || this.State.drivePath;
    const folderName = this._folderEl?.value.trim() || this.State.folderName;

    if (!path) {
      alert('Set the Google Drive root path first.');
      return;
    }

    const btn = this._scanBtn;
    if (btn) { btn.textContent = 'Scanning…'; btn.disabled = true; }

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, folder_name: folderName }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const { scanned, ingested, errors } = data;

      // Refresh library
      await this.catalog.load();

      // Summary message
      let msg = `Scanned ${scanned} ZIP${scanned !== 1 ? 's' : ''}.`;
      if (ingested.length > 0) {
        msg += `\n✓ Imported ${ingested.length} new song${ingested.length !== 1 ? 's' : ''}: ${ingested.join(', ')}`;
      } else {
        msg += '\nNo new songs found.';
      }
      if (errors.length > 0) {
        msg += `\n⚠ ${errors.length} error${errors.length !== 1 ? 's' : ''}:\n${errors.join('\n')}`;
      }
      alert(msg);

    } catch (err) {
      alert(`Scan failed: ${err.message}`);
    } finally {
      if (btn) { btn.textContent = 'Scan Drive'; btn.disabled = false; }
    }
  }
}
