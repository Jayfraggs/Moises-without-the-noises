/**
 * state.js — Single source of truth for mwtn UI state.
 * All modules read/write through this object.
 */

export const State = {
  // Current song
  songId:       null,   // string | null
  manifest:     null,   // object | null
  beats:        null,   // { beats, bars, bpm } | null
  keyInfo:      null,   // { key, scale, lufs, peak_db, dynamic_range } | null

  // Playback
  isPlaying:    false,
  duration:     0,
  currentTime:  0,
  playbackRate: 1.0,
  pitchSemitones: 0,
  loopEnabled:  false,
  loopStart:    0,
  loopEnd:      0,

  // Mixer per-stem: { [stemName]: { volume: 1.0, muted: false, soloed: false } }
  mixer: {},

  // Metronome
  metronomeEnabled:    false,
  metronomeVolume:     0.6,
  metronomeMultiplier: 1.0,
  metronomeBeatsPerBar: -1,
  metronomeCountIn:    0,

  // Export
  exportFormat: 'wav',
  exportClick:  false,

  // Import
  pendingFile:  null,  // File | null
  importJobId:  null,  // string | null
  importState:  null,  // 'uploading' | 'processing' | 'done' | 'error' | null

  // Library
  songs:        [],    // manifest[]
  favoritedIds: new Set(JSON.parse(localStorage.getItem('mwtn:favorites') || '[]')),
  trashedIds:   new Set(JSON.parse(localStorage.getItem('mwtn:trashed') || '[]')),
  viewMode:     'library', // 'library' | 'trash'

  // Settings
  drivePath:   localStorage.getItem('mwtn:drive_path') || '',
  folderName:  localStorage.getItem('mwtn:folder_name') || 'mwtn-outputs',

  // Helpers
  saveFavorites() {
    localStorage.setItem('mwtn:favorites', JSON.stringify([...this.favoritedIds]));
  },
  saveTrashed() {
    localStorage.setItem('mwtn:trashed', JSON.stringify([...this.trashedIds]));
  },
  saveSettings() {
    localStorage.setItem('mwtn:drive_path', this.drivePath);
    localStorage.setItem('mwtn:folder_name', this.folderName);
  },
  isFavorited(songId) { return this.favoritedIds.has(songId); },
  isTrashed(songId)   { return this.trashedIds.has(songId); },
  toggleFavorite(songId) {
    if (this.favoritedIds.has(songId)) this.favoritedIds.delete(songId);
    else this.favoritedIds.add(songId);
    this.saveFavorites();
  },
  toggleTrashed(songId) {
    if (this.trashedIds.has(songId)) this.trashedIds.delete(songId);
    else this.trashedIds.add(songId);
    this.saveTrashed();
  },
};
