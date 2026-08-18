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
