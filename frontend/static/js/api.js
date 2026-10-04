/**
 * api.js — All backend API calls for mwtn.
 * Maps to the FastAPI routes in backend/main.py.
 */

const BASE = '/api';

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
   * Upload a ZIP and ingest it. Returns the manifest.
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
};
