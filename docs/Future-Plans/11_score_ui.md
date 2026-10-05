# Plan 11 — Score and Solfa User Interface

## Motive

The new backend capabilities need a coherent MWTN user experience. Users should be able to move between stems, waveform, note timeline, lyrics, chords, solfa, and conventional notation while maintaining **synchronized playback** and clear visual feedback. This is the integration layer that makes the backend work feel like a product.

---

## Frontend Library Decision: Staff Notation Rendering

Rendering staff notation in the browser requires a dedicated library. **Do not attempt to render staff notation from scratch.**

### Option A — OpenSheetMusicDisplay (OSMD) ⭐ Recommended

| Property | Value |
|---|---|
| **License** | MIT |
| **Input** | MusicXML (string or URL) |
| **Output** | SVG (canvas-based) |
| **Install** | `npm install opensheetmusicdisplay` |
| **Bundle size** | ~500 KB gzipped |
| **Capabilities** | Full MusicXML rendering, lyrics, chord symbols, dynamics, ties, slurs |
| **Playback cursor** | Built-in cursor that advances through notes |
| **Offline** | Yes — pure JS, no CDN required |

**Usage:**
```javascript
import { OpenSheetMusicDisplay } from 'opensheetmusicdisplay';

const osmd = new OpenSheetMusicDisplay(containerRef.current, {
  autoResize: true,
  drawCredits: false,
});
await osmd.load(musicXmlString);
await osmd.render();

// Playback cursor
osmd.cursor.show();
osmd.cursor.next(); // advance on each beat
```

### Option B — VexFlow

| Property | Value |
|---|---|
| **License** | MIT |
| **Input** | Programmatic API (not MusicXML) |
| **Output** | SVG or Canvas |
| **Capabilities** | Staff notation primitives; requires manual layout |
| **Offline** | Yes |

> **Verdict:** VexFlow requires building your own MusicXML parser on top of it. OSMD already handles MusicXML → rendered score. Use OSMD.

### Option C — Verovio (WebAssembly)

| Property | Value |
|---|---|
| **License** | LGPL |
| **Input** | MusicXML or MEI |
| **Output** | SVG |
| **Bundle size** | ~3 MB WASM |
| **Quality** | Highest rendering quality; used in scholarly/professional tools |
| **Offline** | Yes |

> **Verdict:** Best rendering quality but 3 MB WASM bundle is heavy. Consider for a future "high quality view" toggle. Use OSMD for v1.

---

## Score Workspace Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [Staff Notation] [Solfa] [Timeline] [Chord Chart] [Lyrics]    │  ← view tabs
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│               Active View (OSMD / Solfa / Timeline)             │
│                                                                  │
│  ← playback cursor advances in sync with transport              │
│                                                                  │
├──────────┬──────────────────────────────────────────────────────┤
│  Track   │  [Vocals ✓] [Piano ✓] [Bass ✓] [Guitar ✓]           │  ← visibility
│  Select  │  Quality: [Fast ▼]   Score: [Melody ▼]              │
├──────────┴──────────────────────────────────────────────────────┤
│  Status: Score generated (v1)  Quality: ██████░░ 74%            │
│  [🎵 Generate Score] [Export MusicXML] [Export MIDI]            │
│  [Open in MuseScore]                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## View Tabs

### 1. Staff Notation (OSMD)
- Renders the generated MusicXML via OSMD
- Shows: key signature, time signature, tempo, notes, rests, ties, chord symbols, lyrics
- Playback cursor advances beat-by-beat, synchronized to `AudioContext.currentTime`
- Track visibility controls show/hide staves per stem
- Stale score shown with a "Score is outdated — regenerate?" banner

### 2. Solfa View
- Displays `SolfaEvent` array as styled syllables in a horizontal scrolling lane
- Each syllable is a styled `<span>` with:
  - Syllable text (e.g., "Sol")
  - Sub-text: scale degree (e.g., "5")
  - Width proportional to note duration
- Active syllable highlighted (color pulse) during playback
- Low-confidence syllables shown in a muted color
- Rests shown as empty space of proportional width

### 3. Note Timeline
- Horizontal piano-roll style display
- Y-axis: MIDI pitch (or note name)
- X-axis: time (seconds) or beats
- Each note is a colored rectangle; color = confidence (green → yellow → red)
- Playback head advances vertically across the timeline
- This view is the primary home for the correction tools from Plan 10:
  - Click a note to select it
  - Drag to move (pitch up/down or time left/right)
  - Double-click to delete
  - Right-click → context menu: split, merge, change pitch, set as uncertain/ok

### 4. Chord Chart
- Shows chord symbols above a timeline grid
- Each chord block spans its beat duration
- Color-coded by chord quality (major = warm, minor = cool, dominant = accent)
- Tap/click a chord to hear it (future; not required for v1)

### 5. Lyrics View
- Word-level lyric display, styled as karaoke text
- Active word highlighted during playback
- Shows alignment status below each word (aligned, uncertain, manual correction)

---

## Playback Synchronization

All views are synchronized to a single **shared clock** derived from `AudioContext.currentTime`.

```javascript
// In AudioEngine.js — expose currentSongTime
const getCurrentSongTime = () => {
  if (!startContextTime || !audioBuffer) return 0;
  return (audioContext.currentTime - startContextTime) * playbackRate + startSongOffset;
};
```

Each view subscribes to a `usePlaybackClock()` hook that polls `getCurrentSongTime()` at ~60fps via `requestAnimationFrame`.

```javascript
// components/Score/usePlaybackClock.js
const usePlaybackClock = (onTick) => {
  const rafRef = useRef(null);
  const tick = () => {
    onTick(getCurrentSongTime());
    rafRef.current = requestAnimationFrame(tick);
  };
  useEffect(() => {
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);
};
```

OSMD cursor advancement:
```javascript
usePlaybackClock((currentTime) => {
  // Find the current note index in the score at currentTime
  // Advance OSMD cursor to that index
  osmd.cursor.Iterator = getIteratorAtTime(currentTime);
});
```

---

## Score Generation Controls

```
Quality:  [Fast ▼]       — pYIN + basic BPM (existing pipeline)
          [Standard ▼]   — Basic Pitch + madmom beat tracking
          [High Quality ▼] — Piano Kong + WhisperX (piano + vocals only)

Score target: [Melody ▼] [Vocal + Lyrics ▼] [Piano ▼] [Full Score ▼]
```

Score status:
- `not_generated` — Show "Generate Score" button
- `generating` — Show progress bar + current stage label
- `generated` — Show timestamp + version; offer Regenerate
- `stale` — Show "Source data changed — regenerate?" warning
- `user_edited` — Show "Manually edited in MuseScore" badge

---

## Files to Create / Modify

```
frontend/src/
  components/
    Score/
      ScoreWorkspace.jsx        # tab container + layout
      StaffNotationView.jsx     # OSMD wrapper
      SolfaView.jsx             # solfa syllable display
      NoteTimelineView.jsx      # piano roll + correction handles
      ChordChartView.jsx        # chord timeline
      LyricsView.jsx            # karaoke-style lyrics
      ScoreControls.jsx         # generate + export + open-in-musescore buttons
      ScoreStatus.jsx           # quality indicator + staleness warning
      usePlaybackClock.js       # shared clock hook
      useScoreSync.js           # OSMD cursor sync logic
```

Add to `package.json`:
```json
"opensheetmusicdisplay": "^1.8.0"
```

---

## Colab / Mobile Data Implications

The OSMD library adds ~500 KB to the frontend bundle — a one-time download when the user first opens the Score workspace. No recurring data cost. All rendering is local.

---

## Expected Results

- MWTN feels like one integrated musical-analysis workstation, not a collection of separate tools
- Users can listen and simultaneously follow the music in multiple synchronized views
- Solfa and conventional notation stay in sync with playback and with each other
- Users can move from automated analysis to professional editing (MuseScore) in one click

---

## Acceptance Criteria

- [ ] Playback cursor in OSMD advances in sync with audio playback
- [ ] Solfa syllable highlights in sync with the same audio position
- [ ] Score and Solfa views can be toggled without changing the underlying data
- [ ] Stale/outdated scores are clearly indicated
- [ ] Export buttons (MusicXML, MIDI) are accessible from the Score workspace
- [ ] Open in MuseScore launches MuseScore if installed, or falls back to file download
- [ ] Long-running generation jobs show meaningful per-stage progress
- [ ] Note timeline correction handles function for basic pitch/time edits
