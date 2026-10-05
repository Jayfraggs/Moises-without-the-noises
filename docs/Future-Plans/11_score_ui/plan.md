# Feature Plan 11 — Score and Solfa User Interface

## Motive

The new backend capabilities need a coherent MWTN user experience. Users should be able to move between stems, waveform, notes, lyrics, chords, solfa, and conventional notation while maintaining synchronized playback.

## Process

1. Add a dedicated Score workspace/tab.
2. Provide views for:
   - staff notation
   - solfa
   - note timeline
   - chord chart
   - lyrics
3. Synchronize all views to the same playback clock.
4. Highlight the currently playing note.
5. Highlight the corresponding solfa syllable.
6. Highlight the corresponding lyric syllable.
7. Highlight the active chord.
8. Provide track/stem visibility controls.
9. Provide score generation controls:
   - melody
   - vocal
   - piano
   - guitar
   - full score
10. Display:
    - key
    - BPM
    - time signature
    - transcription confidence
11. Provide quality/performance selection.
12. Provide export buttons.
13. Provide `Open in MuseScore`.
14. Clearly show when a score is generated, stale, or manually edited.
15. Add loading/progress states for expensive transcription.
16. Handle errors without losing existing analysis.

## Expected Results

- MWTN feels like one integrated musical-analysis workstation rather than a collection of independent tools.
- Users can listen and visually follow the music.
- Solfa and conventional notation stay synchronized.
- Users can move from automated analysis to professional score editing.

## Acceptance Criteria

- Playback synchronization is consistent across all views.
- Score and solfa can be toggled without changing the underlying data.
- Export actions are obvious.
- Long-running jobs show meaningful progress.
