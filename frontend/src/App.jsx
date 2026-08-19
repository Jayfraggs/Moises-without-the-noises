import { useEffect, useRef, useState, useCallback } from 'react';
import { AudioEngine } from './AudioEngine.js';
import {
  listSongs,
  getManifest,
  stemUrl,
  getNotes,
  deleteSong,
  getLyrics,
  getBeats,
  getKey,
  fetchChords,
} from './api.js';
import { SongSelector } from './components/SongSelector.jsx';
import { StemChannel } from './components/StemControls.jsx';
import { TransportControls } from './components/TransportControls.jsx';
import { ImportSong } from './components/ImportSong.jsx';
import SongInfoBar from './components/SongInfoBar.jsx';
import { LyricsPanel } from './components/LyricsPanel.jsx';
import ChordDisplay from './components/ChordDisplay.jsx';
import SpeedControl from './components/SpeedControl.jsx';
import PitchControl from './components/PitchControl.jsx';
import CountInControl from './components/CountInControl.jsx';
import { exportStemAtPitch, triggerBrowserDownload } from './api.js';
import { useOnboarding } from './hooks/useOnboarding.js';
import { OnboardingWizard } from './components/OnboardingWizard.jsx';
import ExportPanel from './components/ExportPanel.jsx';

export default function App() {
  const [songs, setSongs] = useState([]);
  const [selectedSongId, setSelectedSongId] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [notesByStem, setNotesByStem] = useState({});
  const [lyrics, setLyrics] = useState(null);
  const [bpm, setBpm] = useState(null);
  const [keyInfo, setKeyInfo] = useState(null);
  const [chords, setChords] = useState(null);
  const [bpmLoading, setBpmLoading] = useState(false);
  const [keyLoading, setKeyLoading] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1.0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoadingSong, setIsLoadingSong] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [metronomeEnabled, setMetronomeEnabled] = useState(false);
  const [metronomeVolume, setMetronomeVolume] = useState(0.8);
  const [metronomeAvailable, setMetronomeAvailable] = useState(true);

  // Mirrors AudioEngine's internal mute/solo/volume state for React
  // rendering -- the engine itself doesn't trigger re-renders when its
  // internal state changes, so the UI needs its own copy to reflect
  // button states (is-active classes, fader positions).
  const [stemUiState, setStemUiState] = useState({});

  // [CI-03] Count-in state
  const [countInBeats, setCountInBeats] = useState(() => {
    try {
      return Number(localStorage.getItem('mwtn_count_in_beats') || 0) || 0;
    } catch {
      return 0;
    }
  });
  const [isCountingIn, setIsCountingIn] = useState(false);
  const [currentCountInBeat, setCurrentCountInBeat] = useState(0);
  const countInRafRef = useRef(null);

  // One AudioEngine for the app's lifetime -- see AudioEngine.unloadAll()
  // for why we reuse rather than recreate this on every song switch.
  const engineRef = useRef(null);
  if (!engineRef.current) {
    engineRef.current = new AudioEngine();
  }
  const engine = engineRef.current;

  const { showOnboarding, completeOnboarding } = useOnboarding();

  const refreshSongs = useCallback(async () => {
    try {
      const list = await listSongs();
      setSongs(list);
    } catch (err) {
      setLoadError(err.message);
    }
  }, []);

  useEffect(() => {
    refreshSongs();
  }, [refreshSongs]);

  const handleSelectSong = async (songId) => {
    setIsLoadingSong(true);
    setLoadError(null);
    setIsPlaying(false);
    setLyrics(null);
    setChords(null);
    setBpm(null);
    setKeyInfo(null);
    setBpmLoading(false);
    setKeyLoading(false);
    setMetronomeEnabled(false);
    setMetronomeVolume(0.8);
    setMetronomeAvailable(true);
    engine.setMetronomeEnabled(false);
    // Reset playback rate when selecting a new song
    setPlaybackRate(1.0);
    if (engineRef && engineRef.current) engineRef.current.setPlaybackRate(1.0);

    try {
      engine.unloadAll();

      const m = await getManifest(songId);
      setManifest(m);

      const initialUiState = {};
      const notesMap = {};

      for (const stemName of m.stems) {
        await engine.loadStem(stemName, stemUrl(songId, stemName));
        initialUiState[stemName] = { muted: false, soloed: false, volume: 1.0 };

        if (m.notes_available.includes(stemName)) {
          notesMap[stemName] = await getNotes(songId, stemName);
        } else {
          notesMap[stemName] = [];
        }
      }

      setStemUiState(initialUiState);
      setNotesByStem(notesMap);
      setSelectedSongId(songId);

      setBpmLoading(true);
      setKeyLoading(true);
      Promise.all([
        getBeats(songId)
          .then((data) => {
            const beats = data && Array.isArray(data.beats) ? data : null;
            if (beats) {
              engine.loadBeats(beats);
              setMetronomeAvailable(true);
              setMetronomeEnabled(false);
              engine.setMetronomeEnabled(false);
            } else {
              setMetronomeAvailable(false);
              setMetronomeEnabled(false);
              engine.setMetronomeEnabled(false);
            }
            setBpm(data?.bpm ?? null);
          })
          .catch(() => {
            setBpm(null);
            setMetronomeAvailable(false);
            setMetronomeEnabled(false);
            engine.setMetronomeEnabled(false);
          })
          .finally(() => setBpmLoading(false)),
        getKey(songId)
          .then((data) => setKeyInfo(data))
          .catch(() => setKeyInfo(null))
          .finally(() => setKeyLoading(false)),
        getLyrics(songId)
          .then((data) => setLyrics(data))
          .catch(() => setLyrics({ available: false, segments: [] })),
        fetchChords(songId)
          .then((data) => setChords(data))
          .catch(() => setChords(null)),
      ]);
    } catch (err) {
      setLoadError(`Failed to load song: ${err.message}`);
    } finally {
      setIsLoadingSong(false);
    }
  };

  const handleDeleteSong = async (songId) => {
    if (songId === selectedSongId) {
      engine.unloadAll();
      setSelectedSongId(null);
      setManifest(null);
    }
    await deleteSong(songId);
    refreshSongs();
  };

  const handlePlayPause = () => {
    if (isPlaying) {
      engine.pause();
      setIsPlaying(false);
      // Cancel any count-in UI state
      setIsCountingIn(false);
      setCurrentCountInBeat(0);
    } else {
      // If count-in selected, use startWithCountIn; else regular play
      if (countInBeats > 0) {
        engine.startWithCountIn(countInBeats);
        setIsCountingIn(true);
        setCurrentCountInBeat(0);
      } else {
        engine.play();
        setIsPlaying(true);
      }
    }
  };

  const handleToggleMute = (stemName) => {
    setStemUiState((prev) => {
      const next = { ...prev, [stemName]: { ...prev[stemName], muted: !prev[stemName].muted } };
      engine.setMute(stemName, next[stemName].muted);
      return next;
    });
  };

  const handleToggleSolo = (stemName) => {
    setStemUiState((prev) => {
      const next = { ...prev, [stemName]: { ...prev[stemName], soloed: !prev[stemName].soloed } };
      engine.setSolo(stemName, next[stemName].soloed);
      return next;
    });
  };

  const handleVolumeChange = (stemName, volume) => {
    setStemUiState((prev) => ({ ...prev, [stemName]: { ...prev[stemName], volume } }));
    engine.setVolume(stemName, volume);
  };

  const handleToggleMetronome = () => {
    if (!metronomeAvailable) return;
    const nextEnabled = !metronomeEnabled;
    setMetronomeEnabled(nextEnabled);
    engine.setMetronomeEnabled(nextEnabled);
  };

  const handleMetronomeVolumeChange = (value) => {
    const nextValue = Math.max(0, Math.min(1, value));
    setMetronomeVolume(nextValue);
    engine.setMetronomeVolume(nextValue);
  };

  const handleRateChange = (rate) => {
    if (engineRef && engineRef.current) engineRef.current.setPlaybackRate(rate);
    setPlaybackRate(rate);
  };

  // [CI-03] Persist count-in selection and expose setter
  const handleCountInChange = (n) => {
    setCountInBeats(n);
    try { localStorage.setItem('mwtn_count_in_beats', String(n)); } catch {}
  };

  // [CI-03] Monitor engine._isCountingIn via RAF and update UI counters
  useEffect(() => {
    let rafId = null;
    function step() {
      const eng = engineRef.current;
      if (!eng) {
        rafId = requestAnimationFrame(step);
        return;
      }
      const counting = !!eng._isCountingIn;
      if (counting) {
        setIsCountingIn(true);
        const scheduledStart = eng._playbackStartTime;
        const bpm = eng.bpm || (manifest && manifest.bpm) || null;
        if (scheduledStart && bpm && countInBeats > 0) {
          const interval = 60.0 / bpm;
          const firstClick = scheduledStart - (countInBeats * interval);
          const now = eng.context.currentTime;
          let beatIndex = Math.floor((now - firstClick) / interval) + 1;
          if (beatIndex < 1) beatIndex = 1;
          if (beatIndex > countInBeats) beatIndex = countInBeats;
          setCurrentCountInBeat(beatIndex);
        }
      } else {
        if (isCountingIn) {
          setIsCountingIn(false);
          setCurrentCountInBeat(0);
          // If engine started playback after count-in, reflect that
          if (eng.isPlaying) setIsPlaying(true);
        }
      }
      rafId = requestAnimationFrame(step);
    }
    rafId = requestAnimationFrame(step);
    countInRafRef.current = rafId;
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      countInRafRef.current = null;
    };
  }, [engineRef, countInBeats, isCountingIn, manifest]);

  const [isExporting, setIsExporting] = useState(false);
  // Export panel visibility
  const [showExport, setShowExport] = useState(false);

  const handleSemitoneChange = (semitones) => {
    if (engineRef && engineRef.current && typeof engineRef.current.setPitch === 'function') {
      engineRef.current.setPitch(semitones);
    }
  };

  const handleExportAtPitch = async (semitones) => {
    if (!manifest) return;
    setIsExporting(true);
    try {
      // Export each stem sequentially to avoid hammering the server
      for (const stemName of manifest.stems) {
        try {
          const blob = await exportStemAtPitch(selectedSongId, stemName, semitones);
          const safeTitle = (manifest.title || selectedSongId).replace(/[^a-zA-Z0-9_\- ]/g, '_');
          const filename = `${safeTitle}_${stemName}_${semitones > 0 ? '+' : ''}${semitones}st.wav`;
          triggerBrowserDownload(blob, filename);
        } catch (e) {
          console.error('Export failed for', stemName, e);
        }
        // small pause to be kinder to server
        await new Promise((r) => setTimeout(r, 200));
      }
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="app">
      {showOnboarding && (
        <OnboardingWizard onComplete={completeOnboarding} />
      )}
      <header className="app__header">
        <h1 className="app__title">Stem Practice</h1>
        <p className="app__subtitle">isolate a stem, read the note, play along</p>
      </header>

      <div className="app__body">
        <aside className="app__sidebar">
          <SongSelector
            songs={songs}
            selectedSongId={selectedSongId}
            onSelect={handleSelectSong}
            onDelete={handleDeleteSong}
          />
          <ImportSong onImportComplete={refreshSongs} />
        </aside>

        <main className="app__main">
          {loadError && <div className="app__error">{loadError}</div>}

          {isLoadingSong && <div className="app__loading">Loading stems\u2026</div>}

          {!isLoadingSong && manifest && (
            <>
              <SongInfoBar manifest={manifest} bpm={bpm} keyInfo={keyInfo} bpmLoading={bpmLoading} keyLoading={keyLoading} />

              <TransportControls
                engine={engine}
                isPlaying={isPlaying}
                onPlayPause={handlePlayPause}
                duration={engine.duration}
                metronomeEnabled={metronomeEnabled}
                metronomeVolume={metronomeVolume}
                metronomeAvailable={metronomeAvailable}
                onToggleMetronome={handleToggleMetronome}
                onMetronomeVolumeChange={handleMetronomeVolumeChange}
              />

              {/* Export button (insertion point) */}
              <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowExport(true)}
                  disabled={!selectedSongId}
                >
                  Export
                </button>
              </div>

              <div style={{ marginTop: 10 }}>
                <SpeedControl currentRate={playbackRate} onRateChange={handleRateChange} />
              </div>

              <div style={{ marginTop: 10, display: 'flex', gap: 12, alignItems: 'center' }}>
                <CountInControl
                  onCountInChange={handleCountInChange}
                  isCountingIn={isCountingIn}
                  currentCountInBeat={currentCountInBeat}
                  totalCountInBeats={countInBeats}
                />

                <PitchControl
                  currentKey={keyInfo?.key ?? null}
                  onSemitoneChange={handleSemitoneChange}
                  onExportAtPitch={(n) => handleExportAtPitch(n)}
                />
                {isExporting && <div style={{ color: '#e8a020', marginTop: 8 }}>Exporting stems…</div>}
              </div>

              <div className="mixing-console">
                {manifest.stems.map((stemName) => (
                  <StemChannel
                    key={stemName}
                    name={stemName}
                    muted={stemUiState[stemName]?.muted || false}
                    soloed={stemUiState[stemName]?.soloed || false}
                    volume={stemUiState[stemName]?.volume ?? 1.0}
                    notes={notesByStem[stemName] || []}
                    engine={engine}
                    isPlaying={isPlaying}
                    onToggleMute={handleToggleMute}
                    onToggleSolo={handleToggleSolo}
                    onVolumeChange={handleVolumeChange}
                  />
                ))}
              </div>

              <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', marginTop: 12 }}>
                <ChordDisplay chords={chords} getCurrentTime={() => engine.getCurrentTime()} />
                <LyricsPanel engine={engine} lyrics={lyrics} isPlaying={isPlaying} />
              </div>

              {/* Export panel mount (insertion point) */}
              {showExport && manifest && (
                <ExportPanel
                  songId={selectedSongId}
                  stems={manifest.stems}
                  currentGains={Object.fromEntries((manifest.stems || []).map((s) => [s, stemUiState[s]?.volume ?? 1.0]))}
                  onClose={() => setShowExport(false)}
                />
              )}
            </>
          )}

          {!isLoadingSong && !manifest && (
            <div className="app__empty-state">
              <p>Select a song from the left to start practicing.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
