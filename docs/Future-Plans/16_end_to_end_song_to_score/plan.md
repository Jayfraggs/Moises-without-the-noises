# Feature Plan 16 — End-to-End Song-to-Score Workflow

## Motive

After the individual features are implemented, MWTN needs a single orchestration workflow that turns an existing recording into a usable musical document with minimal manual intervention.

This is the final integration layer and should not be implemented before the underlying contracts are stable.

## Process

1. User imports MP3/WAV/etc.
2. Calculate source hash.
3. Create a project record.
4. Inspect audio properties.
5. Detect initial BPM/key candidates.
6. Select processing profile.
7. Run source separation.
8. Validate stems.
9. Run appropriate transcription models per stem.
10. Run beat/downbeat/rhythm analysis.
11. Run key/scale analysis.
12. Run chord analysis.
13. Align lyrics to vocal notes where available.
14. Merge all outputs into canonical musical events.
15. Run consistency/error checks.
16. Quantize events into notation-ready form.
17. Generate solfa.
18. Generate MIDI.
19. Generate MusicXML.
20. Store all artifacts and metadata.
21. Present score/solfa/chord/lyrics views.
22. Allow user corrections.
23. Regenerate dependent artifacts after corrections.
24. Provide:
   - `Open in MuseScore`
   - `Export MusicXML`
   - `Export MIDI`
   - `Export Solfa`
   - other existing MWTN exports
25. Preserve every processing run as reproducible metadata.

## Expected Results

A user can perform the intended workflow:

> **Drop an existing song into MWTN → wait for analysis → receive stems, notes, chords, lyrics, solfa, MIDI, and an editable MusicXML score → open the score in MuseScore for final engraving/editing.**

The workflow should degrade gracefully. For example, if guitar transcription is unavailable, MWTN should still produce vocal melody, bass, chords, lyrics, solfa, and the parts that succeeded.

## Acceptance Criteria

- One end-to-end test song completes the complete pipeline.
- Every major artifact is present and linked through the manifest.
- The generated MusicXML opens in MuseScore.
- Solfa corresponds to the generated melody.
- MIDI corresponds to the generated note events.
- Playback synchronization works.
- Failed optional stages do not destroy successful stages.
- The entire processing run is reproducible from its manifest.
