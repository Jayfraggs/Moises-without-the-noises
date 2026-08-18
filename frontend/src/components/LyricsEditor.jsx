import React, { useState } from 'react';
import { patchLyrics } from '../api';

function formatTime(sec) {
  if (sec == null || Number.isNaN(sec)) return '--:--:--.---';
  const totalMs = Math.max(0, Math.round(sec * 1000));
  const ms = totalMs % 1000;
  const totalSec = Math.floor(totalMs / 1000);
  const s = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const m = totalMin % 60;
  const h = Math.floor(totalMin / 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function clampStart(start, end) {
  const min = 0;
  const max = Math.max(0, end - 0.05);
  return Math.min(max, Math.max(min, start));
}

export default function LyricsEditor({ songId, words, onSave, onClose, songTitle }) {
  const [localWords, setLocalWords] = useState(() => (words ? words.map(w => ({ ...w })) : []));
  const [saving, setSaving] = useState(false);

  const adjust = (index, delta) => {
    setLocalWords(prev => {
      const copy = prev.map(w => ({ ...w }));
      const item = copy[index];
      if (!item) return prev;
      const newStart = clampStart(Number((item.start + delta).toFixed(3)), item.end);
      item.start = newStart;
      // ensure start is not greater than end - 0.05
      if (item.start > item.end - 0.05) item.start = Math.max(0, item.end - 0.05);
      return copy;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await patchLyrics(songId, localWords);
      if (onSave) onSave(updated);
      if (onClose) onClose();
    } catch (err) {
      // keep modal open and report error
      alert('Failed to save lyrics: ' + (err && err.message ? err.message : String(err)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: '90%', maxWidth: 900, maxHeight: '85vh', background: '#0f0f10', color: '#fff', borderRadius: 8, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.06)', background: '#111' }}>
          <div style={{ fontSize: '1rem', fontWeight: 600 }}>{songTitle || songId}</div>
          <div>
            <button onClick={onClose} style={{ marginRight: 8, padding: '0.4rem 0.6rem' }}>Cancel</button>
            <button onClick={handleSave} disabled={saving} style={{ padding: '0.4rem 0.8rem', background: 'var(--accent, #f0c040)', border: 'none' }}>{saving ? 'Saving…' : 'Save'}</button>
          </div>
        </div>

        <div style={{ padding: '0.75rem 1rem', overflow: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 220px', gap: '0.5rem', alignItems: 'center', fontSize: '0.95rem' }}>
            {localWords.length === 0 && <div style={{ gridColumn: '1 / -1', opacity: 0.7 }}>No lyric words available</div>}
            {localWords.map((w, i) => (
              <React.Fragment key={i}>
                <div style={{ padding: '0.35rem 0.5rem', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                  <div style={{ fontSize: '0.95rem' }}>{w.word}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '0.5rem 0.25rem', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => adjust(i, -0.1)} title="-0.1s">-0.1s</button>
                    <button onClick={() => adjust(i, -0.01)} title="-0.01s">-0.01s</button>
                  </div>
                  <div style={{ minWidth: 140, textAlign: 'center', fontFamily: 'monospace' }}>{formatTime(w.start)}</div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => adjust(i, 0.01)} title="+0.01s">+0.01s</button>
                    <button onClick={() => adjust(i, 0.1)} title="+0.1s">+0.1s</button>
                  </div>
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
