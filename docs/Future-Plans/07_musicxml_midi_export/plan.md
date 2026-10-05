# Feature Plan 07 — MIDI and MusicXML Score Generation

## Motive

MuseScore should receive a structured musical document rather than raw audio. MIDI is useful for playback and interchange, while MusicXML is the primary score-oriented interchange format for notation.

## Process

1. Implement a score-building layer over the canonical musical representation.
2. Group events into logical tracks/staves.
3. Assign instruments.
4. Determine clefs based on track/instrument and register.
5. Apply key signatures.
6. Apply time signatures.
7. Apply tempo information.
8. Convert quantized note events into legal notation durations.
9. Generate rests.
10. Generate ties.
11. Generate voices where simultaneous rhythms require them.
12. Preserve dynamics/velocity when reliable.
13. Add chord symbols.
14. Add lyrics and lyric syllable alignment where available.
15. Add articulations only when supported by reliable source data.
16. Generate MIDI with stable track/channel mapping.
17. Generate MusicXML with valid schema structure.
18. Validate generated MusicXML before exposing it.
19. Store generated files as versioned artifacts.
20. Make generation deterministic for identical source data.
21. Provide separate exports:
   - melody
   - vocal + lyrics
   - piano
   - guitar
   - bass
   - full arrangement
22. Avoid forcing uncertain events into the score without metadata.

## Expected Results

- MWTN can generate editable MIDI.
- MWTN can generate editable MusicXML.
- MusicXML opens correctly in MuseScore.
- Multiple tracks become separate score parts/staves.
- Lyrics and chord symbols can be included where confidence permits.

## Acceptance Criteria

- Generated MIDI imports correctly.
- Generated MusicXML opens in MuseScore without structural errors.
- A simple melody renders with correct pitch and rhythm.
- Multi-track scores preserve track separation.
- Lyrics and chord symbols align with musical positions.
