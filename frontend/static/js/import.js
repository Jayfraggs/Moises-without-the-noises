/**
 * import.js — File drop, file picker, ZIP upload, ingest polling.
 *
 * Accepts:
 *   - ZIP files → POST /api/ingest/upload  (Colab output or raw stems)
 *   - Audio files (.mp3/.wav/etc.) → not yet supported by backend; shows hint
 */
export class Import {
  constructor({ State, API, catalog }) {
    this.State   = State;
    this.API     = API;
    this.catalog = catalog;

    this._fileInput = document.getElementById('fileInput');
    this._filePill  = document.getElementById('filePill');
    this._fileNameEl= document.getElementById('fileName');
    this._fileSizeEl= document.getElementById('fileSize');
    this._fileClear = document.getElementById('fileClear');
    this._dropError = document.getElementById('urlDropError');
    this._jobEl     = document.getElementById('job');
    this._progressEl= document.getElementById('progress');
    this._jobDetail = document.getElementById('job-detail');
    this._jobTitle  = document.getElementById('job-title');
    this._jobStage  = document.getElementById('job-stage');
  }

  init() {
    // File input change
    this._fileInput?.addEventListener('change', () => {
      const file = this._fileInput.files?.[0];
      if (file) this._handleFile(file);
      this._fileInput.value = '';
    });

    // File clear button
    this._fileClear?.addEventListener('click', () => {
      this._clearPill();
      this.State.pendingFile = null;
    });

    // Drag-and-drop on the whole page
    document.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    });

    document.addEventListener('drop', (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) this._handleFile(file);
    });

    // Drag-and-drop indicator on composer
    const composer = document.getElementById('composerWrap');
    composer?.addEventListener('dragenter', () => composer.classList.add('drag-over'));
    composer?.addEventListener('dragleave', () => composer.classList.remove('drag-over'));
    document.addEventListener('drop', () => composer?.classList.remove('drag-over'));
  }

  _handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext === 'zip') {
      this._showPill(file);
      this._uploadZip(file);
    } else if (['mp3','wav','flac','m4a','ogg','opus'].includes(ext)) {
      this._showError('Audio files must be processed through the Colab notebook first. Drop the output ZIP here.');
    } else {
      this._showError(`Unsupported file type: .${ext}. Drop a ZIP from the Colab pipeline.`);
    }
  }

  _showPill(file) {
    this.State.pendingFile = file;
    if (this._fileNameEl) this._fileNameEl.textContent = file.name;
    if (this._fileSizeEl) this._fileSizeEl.textContent = this._fmtSize(file.size);
    this._filePill?.classList.remove('hidden');
    this._clearError();
  }

  _clearPill() {
    this._filePill?.classList.add('hidden');
    if (this._fileNameEl) this._fileNameEl.textContent = '';
    if (this._fileSizeEl) this._fileSizeEl.textContent = '';
  }

  async _uploadZip(file) {
    this._showJob('Uploading ZIP…', 0);

    try {
      const manifest = await this.API.ingestUpload(file, (frac) => {
        this._updateProgress(frac * 0.9);
        this._setStage(`Uploading… ${Math.round(frac * 100)}%`);
      });

      this._updateProgress(1);
      this._setStage('Done!');

      // Add to catalog + auto-select
      this.catalog.addSong(manifest);
      this._clearPill();

      setTimeout(() => {
        this._hideJob();
        this.catalog.selectSong(manifest.song_id);
      }, 600);

    } catch (err) {
      console.error('[import] upload failed:', err);
      this._hideJob();
      this._showError(`Import failed: ${err.message}`);
    }
  }

  _showJob(title, progress) {
    if (this._jobEl)     this._jobEl.classList.remove('hidden');
    if (this._jobTitle)  this._jobTitle.textContent  = title;
    if (this._progressEl) this._progressEl.value     = Math.round(progress * 100);
    if (this._jobDetail) this._jobDetail.textContent  = '';
  }

  _updateProgress(frac) {
    if (this._progressEl) this._progressEl.value = Math.round(frac * 100);
  }

  _setStage(msg) {
    if (this._jobStage) this._jobStage.textContent = msg;
  }

  _hideJob() {
    if (this._jobEl) this._jobEl.classList.add('hidden');
  }

  _showError(msg) {
    if (this._dropError) {
      this._dropError.textContent = msg;
      this._dropError.classList.remove('hidden');
      setTimeout(() => this._clearError(), 6000);
    }
  }

  _clearError() {
    if (this._dropError) {
      this._dropError.textContent = '';
      this._dropError.classList.add('hidden');
    }
  }

  _fmtSize(bytes) {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
}
