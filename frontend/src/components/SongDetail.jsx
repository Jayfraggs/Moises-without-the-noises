import React, { useState, useEffect, useRef } from 'react';
import { TransportControls } from './TransportControls.jsx';
import { getManifest } from '../api.js';

function formatStemName(name) {
  if (!name) return '';
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function PeakMeter({ engine, stemName }) {
  const canvasRef = useRef(null);
  
  useEffect(() => {
    let rafId;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    function draw() {
      if (!canvas) return;
      const rms = engine.getStemRMS ? engine.getStemRMS(stemName) : 0; // Assuming such a method exists, or stub
      
      const width = canvas.width;
      const height = canvas.height;
      
      ctx.clearRect(0, 0, width, height);
      
      ctx.fillStyle = '#1a1a1a';
      ctx.fillRect(0, 0, width, height);
      
      ctx.fillStyle = '#e8a020';
      const levelHeight = Math.min(rms * height * 5, height); // Arbitrary scaling for visual
      ctx.fillRect(0, height - levelHeight, width, levelHeight);
      
      rafId = requestAnimationFrame(draw);
    }
    
    draw();
    
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [engine, stemName]);
  
  return <canvas ref={canvasRef} width={20} height={60} style={{ backgroundColor: '#1a1a1a', borderRadius: 4 }} />;
}

export function SongDetail({ songId, initialManifest, engine, onBack }) {
  const [manifest, setManifest] = useState(initialManifest);
  const [loading, setLoading] = useState(!initialManifest);
  const [error, setError] = useState(null);
  const [stemStates, setStemStates] = useState({});
  const [isPlaying, setIsPlaying] = useState(false);
  
  useEffect(() => {
    if (!initialManifest) {
      setLoading(true);
      getManifest(songId)
        .then(m => {
          setManifest(m);
          initializeStems(m);
          setLoading(false);
        })
        .catch(err => {
          setError(err.message);
          setLoading(false);
        });
    } else {
      initializeStems(initialManifest);
    }
  }, [songId, initialManifest]);

  function initializeStems(m) {
    const states = {};
    m.stems.forEach(stem => {
      states[stem] = { muted: false, solo: false, volume: 1.0 };
    });
    setStemStates(states);
  }

  const handleToggleMute = (stemName) => {
    setStemStates(prev => {
      const next = { ...prev, [stemName]: { ...prev[stemName], muted: !prev[stemName].muted } };
      engine.setMute(stemName, next[stemName].muted);
      return next;
    });
  };

  const handleToggleSolo = (stemName) => {
    setStemStates(prev => {
      const next = { ...prev, [stemName]: { ...prev[stemName], solo: !prev[stemName].solo } };
      engine.setSolo(stemName, next[stemName].solo);
      return next;
    });
  };

  const handleVolumeChange = (stemName, volume) => {
    setStemStates(prev => {
      const next = { ...prev, [stemName]: { ...prev[stemName], volume } };
      engine.setVolume(stemName, volume);
      return next;
    });
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

  if (loading) return <div className="song-detail-loading">Loading song details...</div>;
  if (error) return <div className="song-detail-error">Error: {error}</div>;
  if (!manifest) return null;

  return (
    <div className="song-detail">
      <header className="song-detail__header" style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <button onClick={onBack} className="btn btn-ghost">← Back</button>
        <div>
          <h2 style={{ margin: 0 }}>{manifest.title || songId}</h2>
          <div style={{ display: 'flex', gap: 8, color: '#888', fontSize: '0.9em' }}>
            {manifest.key && <span>Key: {manifest.key}</span>}
            {manifest.bpm && <span>BPM: {manifest.bpm}</span>}
          </div>
        </div>
      </header>

      <div className="song-detail__stems" style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 32 }}>
        {manifest.stems.map(stemName => (
          <div key={stemName} style={{ display: 'flex', alignItems: 'center', gap: 16, background: '#1a1a1a', padding: 12, borderRadius: 6 }}>
            <div style={{ width: 80, fontWeight: 'bold' }}>{formatStemName(stemName)}</div>
            <button 
              className={`btn ${stemStates[stemName]?.solo ? 'btn-active' : ''}`}
              onClick={() => handleToggleSolo(stemName)}
              style={{ background: stemStates[stemName]?.solo ? '#e8a020' : '#242424' }}
            >
              S
            </button>
            <button 
              className={`btn ${stemStates[stemName]?.muted ? 'btn-active' : ''}`}
              onClick={() => handleToggleMute(stemName)}
              style={{ background: stemStates[stemName]?.muted ? '#fd7e6e' : '#242424' }}
            >
              M
            </button>
            <input 
              type="range" 
              min="0" 
              max="1" 
              step="0.01" 
              value={stemStates[stemName]?.volume ?? 1.0}
              onChange={(e) => handleVolumeChange(stemName, parseFloat(e.target.value))}
              style={{ flex: 1 }}
            />
            <PeakMeter engine={engine} stemName={stemName} />
          </div>
        ))}
      </div>

      <TransportControls 
        engine={engine}
        isPlaying={isPlaying}
        onPlayPause={handlePlayPause}
        duration={engine.duration}
        metronomeEnabled={false}
        metronomeVolume={0.8}
        metronomeAvailable={false}
        onToggleMetronome={() => {}}
        onMetronomeVolumeChange={() => {}}
      />

      <div className="song-detail__metadata" style={{ display: 'flex', gap: 8, marginTop: 24 }}>
        <button 
          className="badge" 
          disabled={!manifest.has_lyrics}
          onClick={() => manifest.has_lyrics && console.log('Navigate to Lyrics')}
          style={{ opacity: manifest.has_lyrics ? 1 : 0.5, cursor: manifest.has_lyrics ? 'pointer' : 'default', padding: '4px 8px', borderRadius: 12, background: '#242424', border: 'none', color: '#f0f0f0' }}
        >
          Lyrics {manifest.has_lyrics ? 'Available' : 'Unavailable'}
        </button>
        <button 
          className="badge" 
          disabled={!manifest.notes_available?.length}
          onClick={() => manifest.notes_available?.length && console.log('Navigate to Chords/Notes')}
          style={{ opacity: manifest.notes_available?.length ? 1 : 0.5, cursor: manifest.notes_available?.length ? 'pointer' : 'default', padding: '4px 8px', borderRadius: 12, background: '#242424', border: 'none', color: '#f0f0f0' }}
        >
          Chords/Notes {manifest.notes_available?.length ? 'Available' : 'Unavailable'}
        </button>
        <button 
          className="badge" 
          disabled={!manifest.has_beats}
          onClick={() => manifest.has_beats && console.log('Navigate to Beat Grid')}
          style={{ opacity: manifest.has_beats ? 1 : 0.5, cursor: manifest.has_beats ? 'pointer' : 'default', padding: '4px 8px', borderRadius: 12, background: '#242424', border: 'none', color: '#f0f0f0' }}
        >
          Beat Grid {manifest.has_beats ? 'Available' : 'Unavailable'}
        </button>
      </div>
    </div>
  );
}
