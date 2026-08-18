import { useEffect, useRef, useState } from 'react';

/**
 * Shows the note active at the engine's current playback position, updated
 * via requestAnimationFrame while playing.
 *
 * Notes are precomputed segments: [{start, end, note, midi}, ...], sorted
 * by start time (guaranteed by note_extraction.py's consolidation pass).
 * Since playback position moves forward monotonically during normal
 * playback, we track a cursor index and only re-scan from the start when
 * position jumps backward (a seek/loop) -- this keeps the per-frame lookup
 * O(1) amortized instead of an O(n) linear scan every animation frame.
 */
export function NoteDisplay({ engine, notes, isPlaying, instrumentLabel }) {
  const [currentNote, setCurrentNote] = useState(null);
  const rafRef = useRef(null);
  const cursorRef = useRef(0);
  const lastTimeRef = useRef(0);

  useEffect(() => {
    // Notes changed (different stem selected) -- reset scan position.
    cursorRef.current = 0;
  }, [notes]);

  useEffect(() => {
    if (!isPlaying || !notes || notes.length === 0) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const tick = () => {
      const t = engine.getCurrentTime();

      // Playback jumped backward (seek, loop-back, or scrubbed) -- the
      // cursor's forward-only assumption breaks, so restart the scan.
      if (t < lastTimeRef.current - 0.05) {
        cursorRef.current = 0;
      }
      lastTimeRef.current = t;

      let idx = cursorRef.current;
      // Advance past segments we've already played through.
      while (idx < notes.length - 1 && notes[idx].end <= t) {
        idx++;
      }
      cursorRef.current = idx;

      const seg = notes[idx];
      const active = seg && t >= seg.start && t < seg.end;
      setCurrentNote(active ? seg.note : null);

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, notes, engine]);

  const hasNoteData = notes && notes.length > 0;

  return (
    <div className="tuner-display">
      <div className="tuner-display__label">{instrumentLabel}</div>
      <div className={`tuner-display__note ${currentNote ? 'is-active' : ''}`}>
        {hasNoteData ? currentNote || '\u2014' : 'n/a'}
      </div>
      {!hasNoteData && (
        <div className="tuner-display__hint">no note data for this stem</div>
      )}
    </div>
  );
}
