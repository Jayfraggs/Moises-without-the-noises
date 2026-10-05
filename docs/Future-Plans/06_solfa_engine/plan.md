# Feature Plan 06 — Movable-Do Solfa Extraction and Display

## Motive

The user-facing goal is not merely to produce conventional sheet music. MWTN should be able to turn an existing recording into a practical solfa representation.

Solfa must be derived from musical pitch plus tonal context rather than directly guessed from audio. This makes it consistent with the generated score.

## Process

1. Use the canonical note-event representation as the source.
2. Obtain the active key/scale at every note.
3. Convert each pitch into a scale degree.
4. Support movable-do by default.
5. Support at least:
   - Do
   - Re
   - Mi
   - Fa
   - Sol
   - La
   - Ti
5. Support chromatic alterations:
   - raised/lowered scale degrees
   - optional accidental notation
6. Define how minor keys are represented.
7. Support configurable solfa conventions for regional/user preference where practical.
8. Represent octave/register information separately when needed.
9. Preserve note duration and rhythm.
10. Preserve rests.
11. Support syllable-per-note output.
12. Generate solfa from the same note events used to generate MIDI/MusicXML.
13. If a note's pitch confidence is low, mark the solfa event as uncertain.
14. Recompute solfa automatically when the key is changed.
15. Provide synchronized highlighting against playback.
16. Provide copy/export of solfa.
17. Add an option for fixed-do if later required, while keeping movable-do as the main implementation.

## Expected Results

A melody such as C–D–E–G–E in C major becomes:

`Do Re Mi Sol Mi`

The same musical phrase transposed to D major becomes:

`Do Re Mi Sol Mi`

This makes the system useful for ear training, singing practice, and Nigerian/West African solfa-oriented musical learning workflows.

## Acceptance Criteria

- Solfa is generated from canonical notes rather than independently guessed.
- Changing key changes movable-do output correctly.
- Rhythm is retained.
- Low-confidence notes are marked.
- Solfa playback highlighting follows the corresponding notes.
