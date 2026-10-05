/**
 * state.js — Single source of truth for mwtn UI state.
 */

export const State = {
  // Current song
  songId:       null,
  manifest:     null,
  beats:        null,   // { beats: float[], bars: {start,end,bar_number}[], bpm, duration }
  keyInfo:      null,
  sections:     [],     // normalised section objects from backend

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

  // Stem loading progress (progressive): { [stemName]: 0..1 }
  stemLoadProgress: {},

  // Metronome
  metronomeEnabled:     false,
  metronomeVolume:      0.6,
  metronomeMultiplier:  1.0,
  metronomeBeatsPerBar: -1,   // -1 = auto from bars data
  metronomeCountIn:     0,

  // Beat grid editor
  beatEditMode: false,  // true while the ruler is in drag-edit mode

  // VU meters
  vuVisible: false,

  // Export
  exportFormat:   'wav',
  exportClick:    false,
  exportLoopOnly: false,  // when true AND loopEnabled, pass start/end to backend

  // Import
  pendingFile:  null,
  importJobId:  null,
  importState:  null,

  // Library
  songs:        [],
  favoritedIds: new Set(JSON.parse(localStorage.getItem('mwtn:favorites') || '[]')),
  trashedIds:   new Set(JSON.parse(localStorage.getItem('mwtn:trashed')   || '[]')),
  viewMode:     'library',

  // Settings
  drivePath:  localStorage.getItem('mwtn:drive_path')   || '',
  folderName: localStorage.getItem('mwtn:folder_name')  || 'mwtn-outputs',

  saveFavorites() { localStorage.setItem('mwtn:favorites', JSON.stringify([...this.favoritedIds])); },
  saveTrashed()   { localStorage.setItem('mwtn:trashed',   JSON.stringify([...this.trashedIds])); },
  saveSettings()  {
    localStorage.setItem('mwtn:drive_path',  this.drivePath);
    localStorage.setItem('mwtn:folder_name', this.folderName);
  },
  isFavorited(id) { return this.favoritedIds.has(id); },
  isTrashed(id)   { return this.trashedIds.has(id); },
  toggleFavorite(id) {
    if (this.favoritedIds.has(id)) this.favoritedIds.delete(id);
    else this.favoritedIds.add(id);
    this.saveFavorites();
  },
  toggleTrashed(id) {
    if (this.trashedIds.has(id)) this.trashedIds.delete(id);
    else this.trashedIds.add(id);
    this.saveTrashed();
  },
};
