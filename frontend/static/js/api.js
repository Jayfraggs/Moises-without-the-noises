/**
 * api.js — All backend API calls for mwtn.
 * Maps to the FastAPI routes in backend/main.py.
 */

const BASE = '/api';

export class ApiError extends Error {
  constructor(message, status) { super(message); this.name = 'ApiError'; this.status = status; }
}

async function _download(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail || body.error || res.statusText || `HTTP ${res.status}`;
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), res.status);
  }
  return res.blob();
}

async function _json(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try { const b = await res.json(); detail = b.detail || detail; } catch {}
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json();
}

export const API = {
  // ── Library ────────────────────────────────────────────────────────────────

  async listSongs() {
    return _json(await fetch(`${BASE}/songs`));
  },

  async getManifest(songId) {
    return _json(await fetch(`${BASE}/songs/${songId}/manifest`));
  },

  async downloadMidi(songId) { return _download(`/songs/${encodeURIComponent(songId)}/export/midi`); },
  async downloadMusicXML(songId) { return _download(`/songs/${encodeURIComponent(songId)}/export/musicxml`); },
  async downloadClickTrack(songId) { return _download(`/songs/${encodeURIComponent(songId)}/click-track`); },

  async deleteSong(songId) {
    return _json(await fetch(`${BASE}/songs/${songId}`, { method: 'DELETE' }));
  },

  // ── Stems ──────────────────────────────────────────────────────────────────

  stemUrl(songId, stemName) {
    return `${BASE}/songs/${songId}/stems/${stemName}`;
  },

  async getStemWaveform(songId, stemName, buckets = 1500) {
    const res = await fetch(`${BASE}/songs/${songId}/stems/${stemName}/waveform?buckets=${buckets}`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async getAllPeaks(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/peaks`);
    if (res.status === 404) return null;
    return _json(res);
  },

  // ── Analysis ───────────────────────────────────────────────────────────────

  async getBeats(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/beats`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async patchBeats(songId, beats, bars = []) {
    return _json(await fetch(`${BASE}/songs/${songId}/beats`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ beats, bars }),
    }));
  },

  async resetBeats(songId) {
    return _json(await fetch(`${BASE}/songs/${songId}/beats`, { method: 'DELETE' }));
  },

  async getKey(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/key`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async getKeyMap(songId) {
    const res = await fetch(`${BASE}/songs/${encodeURIComponent(songId)}/keymap`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async patchKey(songId, body) {
    return _json(await fetch(`${BASE}/songs/${encodeURIComponent(songId)}/key`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }));
  },

  async getLyrics(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/lyrics`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async getChords(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/chords`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async detectChords(songId) {
    return _json(await fetch(`${BASE}/songs/${encodeURIComponent(songId)}/chords/detect?force=true`));
  },

  async getSections(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/sections`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async patchSections(songId, sections) {
    return _json(await fetch(`${BASE}/songs/${songId}/sections`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sections }),
    }));
  },

  async getConfig() {
    return _json(await fetch(`${BASE}/config`));
  },

  async getStemPresence(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/stem_presence`);
    if (res.status === 404) return null;
    return _json(res);
  },

  async getSolfa(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/solfa`);
    if (!res.ok) {
      const err = new Error(`${res.status} ${res.statusText}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  },

  async getStemSolfa(songId, stemName) {
    return _json(await fetch(
      `${BASE}/songs/${encodeURIComponent(songId)}/stems/${encodeURIComponent(stemName)}/solfa`,
    ));
  },

  async computeSolfa(songId) {
    const res = await fetch(`${BASE}/songs/${songId}/solfa`, { method: 'POST' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status}`);
    }
    return res.json();
  },

  // ── Import ─────────────────────────────────────────────────────────────────

  /**
   * Upload a ZIP (Colab output) and ingest it. Returns the manifest.
   * onProgress(0..1) called with upload progress.
   */
  ingestUpload(file, onProgress = null) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/ingest/upload`);
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { reject(new Error('Invalid JSON from server')); }
        } else {
          let detail = xhr.statusText;
          try { detail = JSON.parse(xhr.responseText).detail || detail; } catch {}
          reject(new Error(`${xhr.status}: ${detail}`));
        }
      };
      xhr.onerror = () => reject(new Error('Network error uploading ZIP'));
      xhr.send(form);
    });
  },

  /**
   * Upload an audio file for local background separation.
   * Returns { job_id, song_id }.
   * onProgress(0..1) called with upload progress.
   */
  localImport(file, model = 'htdemucs_6s', onProgress = null) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE}/import?model=${encodeURIComponent(model)}`);
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { reject(new Error('Invalid JSON from server')); }
        } else {
          let detail = xhr.statusText;
          try { detail = JSON.parse(xhr.responseText).detail || detail; } catch {}
          reject(new Error(`${xhr.status}: ${detail}`));
        }
      };
      xhr.onerror = () => reject(new Error('Network error uploading audio file'));
      xhr.send(form);
    });
  },

  /**
   * Poll a local import job.
   * Returns { state, status_message, song_id, error, log }
   */
  async importJobStatus(jobId) {
    return _json(await fetch(`${BASE}/import/${encodeURIComponent(jobId)}/status`));
  },

  // ── Export ─────────────────────────────────────────────────────────────────

  mixdownUrl(songId, { stems, gains, ext = 'wav', click = false, clickGain = 0.6 } = {}) {
    const qs = new URLSearchParams({
      stems: stems.join(','),
      gains: gains.map(g => g.toFixed(4)).join(','),
      click: click ? '1' : '0',
      click_gain: String(clickGain),
    });
    return `${BASE}/songs/${songId}/mixdown.${ext}?${qs}`;
  },

  stemsZipUrl(songId, fmt = 'wav') {
    return `${BASE}/songs/${songId}/stems/all.zip?format=${fmt}`;
  },

  triggerDownload(url, filename) {
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  },

  // ── Vocal split ────────────────────────────────────────────────────────────

  /**
   * Trigger a second-pass vocal split on an already-separated song.
   * Splits vocals.wav → lead_vocals.wav + backing_vocals.wav.
   * Requires audio-separator[cpu] in the backend environment.
   * Returns { new_stems: [...], log: [...] }
   */
  async triggerVocalSplit(songId) {
    return _json(await fetch(`${BASE}/songs/${songId}/vocal-split`, { method: 'POST' }));
  },

  // ── Section detection ───────────────────────────────────────────────────────

  /**
   * Trigger automatic section detection using the allin1 ML model
   * (falls back to librosa heuristic if allin1 is not installed).
   * Returns { sections: [...], log: [...] }
   */
  async detectSections(songId) {
    return _json(await fetch(`${BASE}/songs/${songId}/sections/detect`, { method: 'POST' }));
  },

  // ── Setup ──────────────────────────────────────────────────────────────────

  async setupCheck() {
    return _json(await fetch(`${BASE}/setup/check`));
  },

  async setupSave(settings) {
    return _json(await fetch(`${BASE}/setup/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }));
  },

  async setupInstall(engine) {
    return _json(await fetch(`${BASE}/setup/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine }),
    }));
  },

  async setupInstallStatus(jobId) {
    return _json(await fetch(`${BASE}/setup/install/${encodeURIComponent(jobId)}/status`));
  },
};
