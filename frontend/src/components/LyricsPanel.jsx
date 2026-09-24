import React, { useEffect, useRef, useMemo } from 'react';

export default function LyricsPanel({ words, getCurrentTime, isPlaying }) {
  const rafRef = useRef(null);
  const cursorRef = useRef(0);
  const lastTimeRef = useRef(0);
  const prevActiveRef = useRef(-1);
  const wordRefs = useRef([]);
  const lineRefs = useRef([]);
  const prevActiveLineRef = useRef(-1);

  // Build lines: either from explicit line info or fallback to 8 words/line
  const { lines, indexToLine } = useMemo(() => {
    if (!words || words.length === 0) return { lines: [], indexToLine: [] };

    // If any word has an explicit `line` property, use it
    const hasLineProp = words.some(w => w && typeof w.line === 'number');
    if (hasLineProp) {
      const map = new Map();
      words.forEach((w, i) => {
        const li = w.line || 0;
        if (!map.has(li)) map.set(li, []);
        map.get(li).push(i);
      });
      const sorted = Array.from(map.keys()).sort((a, b) => a - b);
      const lines = sorted.map(k => map.get(k).map(idx => words[idx]));
      const indexToLine = [];
      sorted.forEach((k, lineIdx) => {
        map.get(k).forEach(idx => (indexToLine[idx] = lineIdx));
      });
      return { lines, indexToLine };
    }

    // If any word contains a newline marker in the `word` text, split there
    const hasNewline = words.some(w => typeof w.word === 'string' && w.word.includes('\n'));
    if (hasNewline) {
      const lines = [];
      const indexToLine = [];
      let current = [];
      words.forEach((w, i) => {
        const parts = (w.word || '').split('\n');
        // first part stays in current line
        current.push({ ...w, word: parts[0] });
        indexToLine[i] = lines.length;
        if (parts.length > 1) {
          lines.push(current);
          current = [];
          // if there are multiple newlines, treat subsequent parts as empty-word words
          for (let p = 1; p < parts.length; p++) {
            if (parts[p] !== '') current.push({ ...w, word: parts[p] });
          }
        }
      });
      if (current.length) lines.push(current);
      return { lines, indexToLine };
    }

    // Fallback: group every 8 words
    const perLine = 8;
    const lines = [];
    const indexToLine = [];
    for (let i = 0; i < words.length; i += perLine) {
      const chunk = words.slice(i, i + perLine);
      lines.push(chunk);
      chunk.forEach((_, j) => (indexToLine[i + j] = lines.length - 1));
    }
    return { lines, indexToLine };
  }, [words]);

  useEffect(() => {
    // reset refs when words change
    cursorRef.current = 0;
    lastTimeRef.current = 0;
    prevActiveRef.current = -1;
    prevActiveLineRef.current = -1;
    wordRefs.current = [];
    lineRefs.current = [];
  }, [words]);

  useEffect(() => {
    if (!isPlaying || !words || words.length === 0) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const tick = () => {
      const t = (typeof getCurrentTime === 'function') ? getCurrentTime() : 0;

      // seek backwards detection
      if (t < lastTimeRef.current - 0.05) cursorRef.current = 0;
      lastTimeRef.current = t;

      let idx = cursorRef.current;
      while (idx < words.length - 1 && words[idx].end <= t) idx++;
      cursorRef.current = idx;

      const seg = words[idx];
      const isActive = !!seg && t >= seg.start && t < seg.end;
      const newActive = isActive ? idx : -1;
      const prevActive = prevActiveRef.current;

      if (newActive !== prevActive) {
        // Update classes for all words based on newActive
        for (let i = 0; i < (wordRefs.current.length || 0); i++) {
          const el = wordRefs.current[i];
          if (!el) continue;
          if (i < newActive) {
            el.classList.add('lyric-word--past');
            el.classList.remove('lyric-word--active');
          } else if (i === newActive) {
            el.classList.add('lyric-word--active');
            el.classList.remove('lyric-word--past');
          } else {
            el.classList.remove('lyric-word--past');
            el.classList.remove('lyric-word--active');
          }
        }

        // handle auto-scroll at line granularity
        const newLine = newActive >= 0 ? indexToLine[newActive] : -1;
        if (newLine !== prevActiveLineRef.current && newLine >= 0) {
          const lineEl = lineRefs.current[newLine];
          if (lineEl && typeof lineEl.scrollIntoView === 'function') {
            try {
              lineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (e) {
              // ignore scroll errors in some browsers/environments
            }
          }
          prevActiveLineRef.current = newLine;
        }

        prevActiveRef.current = newActive;
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, words, getCurrentTime, indexToLine]);

  // Render
  if (!words || words.length === 0) {
    return (
      <div className="lyrics-panel lyrics-panel--empty">No lyrics available</div>
    );
  }

  return (
    <div className="lyrics-panel" style={{ background: '#111', color: '#fff', padding: '1rem', borderRadius: 6 }}>
      <style>{`\n        .lyrics-panel { font-size: 2rem; line-height: 1.4; max-height: 40vh; overflow: auto; }\n        .lyrics-line { margin: 0.5rem 0; display: flex; flex-wrap: wrap; justify-content: center; }\n        .lyric-word { margin: 0 0.25rem; white-space: pre; transition: opacity 120ms linear, background-color 120ms linear, color 120ms linear; }\n        .lyric-word--past { opacity: 0.5; }\n        .lyric-word--active { background: var(--accent, #f0c040); color: #000; padding: 0.1rem 0.35rem; border-radius: 0.25rem; }\n        .lyrics-panel--empty { font-size: 1rem; opacity: 0.7; }\n      `}</style>

      {lines.map((lineWords, lineIdx) => (
        <div
          key={lineIdx}
          className="lyrics-line"
          data-line-index={lineIdx}
          ref={el => (lineRefs.current[lineIdx] = el)}
        >
          {lineWords.map((w, wi) => {
            // Determine the global index of this word. We must find the correct index in the original words array.
            // Since lines were built from originals, map by identity: find first matching by start/end/word not already used.
            let globalIndex = -1;
            // Try to find matching index by searching words array for an entry that matches
            // (start and end and word). This is O(n) but only in render.
            for (let i = 0; i < words.length; i++) {
              if (words[i] && words[i].start === w.start && words[i].end === w.end && words[i].word === w.word) {
                // ensure not already assigned to a different spot
                if (!indexToLine || indexToLine[i] === undefined || indexToLine[i] === lineIdx) {
                  globalIndex = i;
                  break;
                }
              }
            }

            const idx = globalIndex >= 0 ? globalIndex : `${lineIdx}-${wi}`;

            return (
              <span
                key={idx}
                data-index={idx}
                className="lyric-word"
                ref={el => {
                  // Only store refs for numeric indices
                  if (typeof idx === 'number') wordRefs.current[idx] = el;
                }}
              >
                {w.word}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

// Named export so App.jsx can import { LyricsPanel } as well as the default.
export { LyricsPanel };
