# Feature Plan 04 — Beat, Tempo, Meter and Musical Quantization

## Motive

Raw transcription gives events in seconds. Professional notation needs musical positions: measures, beats, subdivisions, durations, rests, tuplets, and time signatures. MWTN therefore needs a dedicated rhythm layer before reliable MusicXML or engraved notation can be produced.

## Process

1. Preserve the existing BPM detector as one analysis source.
2. Add beat tracking rather than relying only on a single BPM value.
3. Detect downbeats where possible.
4. Support tempo changes rather than assuming one global BPM.
5. Detect or allow user selection of time signature.
6. Build a beat grid from detected timing.
7. Represent tempo as a time-varying map where necessary.
8. Map raw note start/end times onto beat positions.
9. Implement configurable quantization strength.
10. Do not destructively overwrite raw timing.
11. Store:
    - raw timing
    - quantized timing
    - quantization confidence
12. Implement duration normalization:
    - whole
    - half
    - quarter
    - eighth
    - sixteenth
    - dotted values
    - ties
    - rests
13. Detect notes crossing bar boundaries and represent them using ties.
14. Detect likely triplets and other common subdivisions where model confidence supports them.
15. Implement humanization tolerance so expressive performances are not aggressively flattened.
16. Generate measure boundaries.
17. Validate that generated measures contain legal rhythmic totals.
18. Provide a manual correction path for ambiguous meter/quantization.

## Expected Results

- Transcribed events can be expressed as conventional musical rhythm.
- Generated notation has valid measures.
- Timing errors can be corrected without destroying the original transcription.
- Fast expressive passages are not automatically forced into obviously incorrect quantization.
- MusicXML generation has a reliable rhythmic foundation.

## Acceptance Criteria

- A simple 4/4 test melody produces correct measures and note values.
- Notes crossing measures generate valid ties.
- Tempo changes can be represented.
- Quantization can be toggled or adjusted.
- Raw and quantized timing remain separately recoverable.
