// Thin wrapper around the backend API. No base URL configuration needed --
// in dev, Vite's proxy (vite.config.js) forwards /api to localhost:8000;
// in the packaged app, FastAPI serves this frontend itself, same origin.

const BASE = '/api';

async function jsonOrThrow(response) {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON, fall back to statusText
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

export async function listSongs() {
  const res = await fetch(`${BASE}/songs`);
  return jsonOrThrow(res);
}

export async function getManifest(songId) {
  const res = await fetch(`${BASE}/songs/${songId}/manifest`);
  return jsonOrThrow(res);
}

export function stemUrl(songId, stemName) {
  return `${BASE}/songs/${songId}/stems/${stemName}`;
}

export async function getNotes(songId, stemName) {
  const res = await fetch(`${BASE}/songs/${songId}/notes/${stemName}`);
  return jsonOrThrow(res);
}

export async function getLyrics(songId) {
  const res = await fetch(`${BASE}/songs/${songId}/lyrics`);
  return jsonOrThrow(res);
}

export async function getBeats(songId) {
  const res = await fetch(`${BASE}/songs/${songId}/beats`);
  return jsonOrThrow(res);
}

export async function getKey(songId) {
  const res = await fetch(`${BASE}/songs/${songId}/key`);
  return jsonOrThrow(res);
}

export async function fetchChords(songId) {
  const res = await fetch(`${BASE}/songs/${songId}/chords`);
  if (res.status === 404) return null;
  return jsonOrThrow(res);
}

export async function deleteSong(songId) {
  const res = await fetch(`${BASE}/songs/${songId}`, { method: 'DELETE' });
  return jsonOrThrow(res);
}

export async function importSong(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE}/import`, { method: 'POST', body: formData });
  return jsonOrThrow(res);
}

export async function getImportStatus(jobId) {
  const res = await fetch(`${BASE}/import/${jobId}/status`);
  return jsonOrThrow(res);
}

export async function ingestZip(zipPath) {
  const res = await fetch(`${BASE}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zip_path: zipPath }),
  });
  return jsonOrThrow(res);
}

export async function patchLyrics(songId, words) {
  const res = await fetch(`${BASE}/songs/${songId}/lyrics`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ words }),
  });
  return jsonOrThrow(res);
}

// Export a stem at a given pitch (server-side export endpoint)
export async function exportStemAtPitch(songId, stemName, semitones) {
  const qs = new URLSearchParams({ semitones: String(semitones) });
  const res = await fetch(`${BASE}/songs/${songId}/stems/${stemName}/export?${qs.toString()}`);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  const blob = await res.blob();
  return blob;
}

export function triggerBrowserDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportMix(songId, stemGains, includeClick) {
  const res = await fetch(`${BASE}/songs/${songId}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stem_gains: stemGains, include_click: includeClick }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(`${res.status}: ${detail}`);
  }
  const blob = await res.blob();
  return blob;
}
