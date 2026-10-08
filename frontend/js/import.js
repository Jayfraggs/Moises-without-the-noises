/**
 * import.js — File drop, file picker, ZIP upload, and local audio import.
 *
 * Accepts:
 *   - ZIP files → POST /api/ingest/upload  (Colab output or raw stems)
 *   - Audio files (.mp3/.wav/.flac/.m4a/.ogg/.opus)
 *       → POST /api/import  (local separation background job)
 *       → polls GET /api/import/{job_id}/status until done
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
      return;
    }

    if (['mp3', 'wav', 'flac', 'm4a', 'ogg', 'opus'].includes(ext)) {
      this._showPill(file);
      this._localImport(file);
      return;
    }

    this._showError(`Unsupported file type: .${ext}. Drop a ZIP from Colab or an audio file for local separation.`);
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

  // ── Colab ZIP path ──────────────────────────────────────────────────────────

  async _uploadZip(file) {
    this._showJob('Uploading ZIP…', 0);

    try {
      const manifest = await this.API.ingestUpload(file, (frac) => {
        this._updateProgress(frac * 0.9);
        this._setStage(`Uploading… ${Math.round(frac * 100)}%`);
      });

      this._updateProgress(1);
      this._setStage('Done!');

      this.catalog.addSong(manifest);
      this._clearPill();

      setTimeout(() => {
        this._hideJob();
        this.catalog.selectSong(manifest.song_id);
      }, 600);

    } catch (err) {
      console.error('[import] ZIP upload failed:', err);
      this._hideJob();
      this._showError(`Import failed: ${err.message}`);
    }
  }

  // ── Local separation path ───────────────────────────────────────────────────

  async _localImport(file) {
    // Get the selected model from extract modal if available, else default
    const modelSelect = document.getElementById('extractModelSelect');
    const model = modelSelect?.value || 'htdemucs_6s';

    this._showJob(`Starting local separation (${model})…`, 0);
    this._setStage('Uploading audio file…');

    let jobId, songId;
    try {
      const result = await this.API.localImport(file, model, (frac) => {
        this._updateProgress(frac * 0.05); // upload is 5% of total
      });
      jobId  = result.job_id;
      songId = result.song_id;
    } catch (err) {
      this._hideJob();
      this._showError(`Failed to start local import: ${err.message}`);
      return;
    }

    // Poll job status
    this._setStage('Separating stems… (this takes a while on CPU)');
    let done = false;
    while (!done) {
      await new Promise(r => setTimeout(r, 1500));
      try {
        const status = await this.API.importJobStatus(jobId);
        const msg = status.status_message || '';
        this._setStage(msg);

        // Rough progress heuristic based on known pipeline stages
        const progress = this._guessProgress(msg);
        this._updateProgress(0.05 + progress * 0.93);

        if (status.state === 'done') {
          done = true;
          this._updateProgress(1);
          this._setStage('Done!');
          // Fetch the manifest and add to catalog
          try {
            const manifest = await this.API.getManifest(songId);
            this.catalog.addSong(manifest);
            this._clearPill();
            setTimeout(() => {
              this._hideJob();
              this.catalog.selectSong(songId);
            }, 800);
          } catch (e) {
            this._hideJob();
            this._showError(`Separation done but failed to load song: ${e.message}`);
          }
        } else if (status.state === 'error') {
          done = true;
          this._hideJob();
          this._showError(`Separation failed: ${status.error || 'Unknown error'}`);
          this._clearPill();
        }
      } catch (err) {
        // Network blip — keep polling
        console.warn('[import] poll error (retrying):', err);
      }
    }
  }

  /**
   * Map known progress messages to a 0-1 fraction.
   * These match the prog() calls in main.py's _run_import.
   */
  _guessProgress(msg) {
    const m = msg.toLowerCase();
    if (m.includes('running demucs') || m.includes('running spleeter') ||
        m.includes('running mdx') || m.includes('separating'))      return 0.05;
    if (m.includes('note detection'))                                return 0.60;
    if (m.includes('waveform peaks'))                                return 0.70;
    if (m.includes('detecting bpm'))                                 return 0.78;
    if (m.includes('bpm:'))                                          return 0.83;
    if (m.includes('detecting key'))                                 return 0.86;
    if (m.includes('key:'))                                          return 0.90;
    if (m.includes('transcrib') || m.includes('whisper'))           return 0.92;
    if (m.includes('lyrics transcribed'))                            return 0.97;
    if (m.includes('writing manifest') || m.includes('done'))        return 1.00;
    return 0.10; // default during separation
  }

  // ── Job UI helpers ──────────────────────────────────────────────────────────

  _showJob(title, progress) {
    if (this._jobEl)      this._jobEl.classList.remove('hidden');
    if (this._jobTitle)   this._jobTitle.textContent  = title;
    if (this._progressEl) this._progressEl.value      = Math.round(progress * 100);
    if (this._jobDetail)  this._jobDetail.textContent  = '';
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
      setTimeout(() => this._clearError(), 8000);
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
