# Feature Plan 05 — Key, Scale, Chord and Harmonic Analysis

## Motive

Key detection already exists in MWTN, but complete score and solfa generation require a stronger harmonic context. Solfa depends on the tonal center, while chord notation requires chord events aligned to musical time.

## Process

1. Audit the existing key-detection implementation.
2. Define a canonical key object:
   - tonic
   - mode
   - confidence
   - analysis range
3. Support local key changes/modulations.
4. Define a chord event structure:
   - root
   - quality
   - extensions/alterations when known
   - inversion/bass note
   - start/end
   - confidence
5. Implement chord detection as a separate pipeline.
6. Use harmonic information from separated stems and/or full mix depending on the selected algorithm.
7. Allow chord candidates rather than forcing uncertain detections.
8. Align chords to the beat grid.
9. Validate chord sequences against detected notes when possible.
10. Represent enharmonic spelling decisions separately from raw pitch.
11. Provide user correction of key and chords.
12. Recompute dependent solfa when the key changes.
13. Record whether a key/chord result was automatically detected or manually overridden.

## Expected Results

- MWTN knows not only the global key but the tonal context throughout a song.
- Chord charts can be generated.
- Solfa can use the correct tonic/scale.
- Transpositions can preserve functional relationships.
- Users can correct harmonic analysis without rerunning audio separation.

## Acceptance Criteria

- Global key is represented with confidence.
- Chord events align to musical positions.
- Key changes can be represented.
- Manual key correction triggers dependent recalculation.
- Chord confidence is visible to downstream systems.
