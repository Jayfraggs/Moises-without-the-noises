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
import { useOnboarding } from './hooks/useOnboarding.js';
import { OnboardingWizard } from './components/OnboardingWizard.jsx';

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
    } else {
      engine.play();
      setIsPlaying(true);
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

              <div style={{ marginTop: 10 }}>
                <SpeedControl currentRate={playbackRate} onRateChange={handleRateChange} />
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
