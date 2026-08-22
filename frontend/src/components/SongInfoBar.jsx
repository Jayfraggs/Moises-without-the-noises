import React from 'react';
import './SongInfoBar.css';

const SongInfoBar = ({ manifest, bpm, keyInfo, bpmLoading, keyLoading }) => {
  // Transform note notation from backend format (e.g., "Ab", "F#") to display format
  // Only replaces 'b' or '#' that immediately follow a capital letter A-G
  const transformNoteNotation = (noteStr) => {
    if (!noteStr) return noteStr;
    return noteStr.replace(/([A-G])b/g, '$1♭').replace(/([A-G])#/g, '$1♯');
  };

  // Format BPM display: prefer manifest.bpm if available, else fall back to bpm prop
  const getBpmDisplay = () => {
    if (bpmLoading) return 'detecting…';
    const bpmValue = manifest?.bpm ?? bpm;
    if (bpmValue === null || bpmValue === undefined) return '— BPM';
    return `♩ ${Math.round(bpmValue)} BPM`;
  };

  // Format Key display: handle loading state, null state, and keyInfo value
  const getKeyDisplay = () => {
    if (keyLoading) return 'detecting…';
    if (!keyInfo) return '—';
    const transformedKey = transformNoteNotation(keyInfo.key);
    const mode = keyInfo.mode.charAt(0).toUpperCase() + keyInfo.mode.slice(1).toLowerCase();
    return `${transformedKey} ${mode}`;
  };

  return (
    <div className="song-info-bar">
      <div className="badge bpm-badge">
        {getBpmDisplay()}
      </div>
      <div className="badge key-badge">
        {getKeyDisplay()}
      </div>
    </div>
  );
};

export default SongInfoBar;
