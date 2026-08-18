import { useEffect, useRef, useState } from 'react';

export default function ChordDisplay({ chords, getCurrentTime }) {
  const [currentChord, setCurrentChord] = useState(null);
  const rafRef = useRef(null);
  const cursorRef = useRef(0);
  const lastTimeRef = useRef(0);

  useEffect(() => {
    // Reset scan position when chord list changes
    cursorRef.current = 0;
  }, [chords]);

  useEffect(() => {
    if (!chords || chords.length === 0) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      setCurrentChord(null);
      return;
    }

    const tick = () => {
      const t = typeof getCurrentTime === 'function' ? getCurrentTime() : 0;

      // Playback jumped backward (seek) — reset cursor
      if (t < lastTimeRef.current - 0.05) cursorRef.current = 0;
      lastTimeRef.current = t;

      // Linear scan forward from cursor (amortized fast for short songs)
      let idx = cursorRef.current;
      while (idx < chords.length - 1 && chords[idx].end <= t) idx++;
      // If we moved backward (seek), ensure index is not past t
      while (idx > 0 && chords[idx].start > t) idx--;
      cursorRef.current = idx;

      const seg = chords[idx];
      const active = seg && t >= seg.start && t < seg.end;
      setCurrentChord(active ? seg : null);

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [chords, getCurrentTime]);

  if (!chords || chords.length === 0) {
    return (
      <div style={{ color: '#7a7a7a', fontStyle: 'italic' }}>Chord detection unavailable</div>
    );
  }

  // Determine index of current chord for context strip
  const currentIndex = currentChord ? chords.indexOf(currentChord) : -1;
  const prev = currentIndex > 0 ? chords[currentIndex - 1] : null;
  const next = currentIndex >= 0 && currentIndex < chords.length - 1 ? chords[currentIndex + 1] : null;

  const qualityLabel = (name) => {
    if (!name) return '';
    return name.slice(-1).toLowerCase() === 'm' ? 'minor' : 'major';
  };

  const conf = currentChord ? Math.max(0, Math.min(1, currentChord.confidence ?? 0)) : 0;
  const barColor = conf >= 0.7 ? '#59b85a' : conf >= 0.5 ? '#e6c23c' : '#9aa0a6';

  return (
    <div style={{ textAlign: 'center', color: '#e6eef3', fontFamily: 'monospace' }}>
      <div style={{ fontSize: '3rem', lineHeight: 1 }}>{currentChord ? currentChord.chord : '\u2014'}</div>
      <div style={{ fontSize: '0.9rem', color: '#9aa0a6', marginTop: 4 }}>{currentChord ? qualityLabel(currentChord.chord) : ''}</div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 10, alignItems: 'center' }}>
        <div style={{ color: '#6b6f73' }}>{prev ? prev.chord : '\u2014'}</div>
        <div style={{ fontWeight: '700', color: '#ffffff' }}>{currentChord ? currentChord.chord : '\u2014'}</div>
        <div style={{ color: '#6b6f73' }}>{next ? next.chord : '\u2014'}</div>
      </div>

      <div style={{ height: 6, background: '#2b2f33', borderRadius: 3, marginTop: 10, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${conf * 100}%`, background: barColor }} />
      </div>
    </div>
  );
}
