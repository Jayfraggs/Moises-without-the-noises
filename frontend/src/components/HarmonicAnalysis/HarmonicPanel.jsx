import { useCallback, useEffect, useState } from 'react';
import { API_BASE } from '../../api';
import ChordChart from './ChordChart';
import KeyDisplay from './KeyDisplay';

const apiUrl = (path) => `${API_BASE || ''}${path}`;

async function request(path, options) {
  const response = await fetch(apiUrl(path), options);
  if (!response.ok) throw new Error(`Harmonic analysis request failed (${response.status})`);
  return response.json();
}

export default function HarmonicPanel({ songId, currentTime = 0, duration = 0, isVisible = true }) {
  const [keyMap, setKeyMap] = useState([]);
  const [chords, setChords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  const fetchKeyMap = useCallback(async () => {
    const data = await request(`/api/songs/${encodeURIComponent(songId)}/keymap`);
    setKeyMap(data.key_map || []);
  }, [songId]);

  const fetchChords = useCallback(async () => {
    const data = await request(`/api/songs/${encodeURIComponent(songId)}/chords`);
    setChords(Array.isArray(data) ? data : (data.chords || []));
  }, [songId]);

  useEffect(() => {
    if (!songId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchKeyMap(), fetchChords()]).catch((cause) => {
      if (!cancelled) setError(cause.message);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [songId, fetchKeyMap, fetchChords]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      await request(`/api/songs/${encodeURIComponent(songId)}/chords/detect?force=true`);
      await fetchChords();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleKeyOverride = async (tonic, mode, start_s, end_s) => {
    try {
      await request(`/api/songs/${encodeURIComponent(songId)}/key`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tonic, mode, start_s, end_s }) });
      await fetchKeyMap();
    } catch (cause) { setError(cause.message); }
  };

  const handleChordOverride = async (chordId, root, quality) => {
    try {
      await request(`/api/songs/${encodeURIComponent(songId)}/chords/${encodeURIComponent(chordId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root, quality }) });
      await fetchChords();
    } catch (cause) { setError(cause.message); }
  };

  if (!isVisible) return null;
  return (
    <section className="harmonic-panel" aria-label="Harmonic Analysis">
      <header className="harmonic-panel__header">
        <h2>Harmonic Analysis</h2>
        <button type="button" onClick={handleAnalyze} disabled={analyzing || loading}>{analyzing ? 'Analyzing…' : 'Analyze'}</button>
      </header>
      {error && <p className="harmonic-error" role="alert">{error}</p>}
      <KeyDisplay keyMap={keyMap} currentTime={currentTime} songId={songId} onKeyOverride={handleKeyOverride} />
      <div className="harmonic-panel__section"><h3>Chord Chart</h3>
        {chords.length ? <ChordChart chords={chords} currentTime={currentTime} duration={duration} onChordOverride={handleChordOverride} /> : !loading && <div className="harmonic-empty"><p>No chord analysis yet.</p><button type="button" onClick={handleAnalyze}>Detect Chords</button></div>}
      </div>
    </section>
  );
}
