# Feature Plan 14 — Automated Testing, Musical Validation and Benchmarking

## Motive

Audio transcription can fail in subtle musical ways while still producing technically valid files. Conventional unit tests are necessary but insufficient. MWTN needs a test corpus and musical validation framework.

## Process

1. Create synthetic test audio with known:
   - pitches
   - rhythms
   - chords
   - tempo
   - key
   - lyrics
2. Create a small curated real-world test set where licensing permits.
3. Test separation outputs.
4. Test monophonic transcription.
5. Test polyphonic transcription.
6. Test beat tracking.
7. Test quantization.
8. Test key detection.
9. Test chord detection.
10. Test solfa conversion.
11. Test MIDI generation.
12. Test MusicXML generation.
13. Open generated MusicXML in a validation environment.
14. Compare predicted notes against ground truth using suitable musical metrics.
15. Measure:
   - pitch accuracy
   - onset accuracy
   - offset accuracy
   - note F1
   - chord accuracy
   - key accuracy
   - lyric alignment error
16. Test low-confidence handling.
17. Test long audio.
18. Test silence and noisy audio.
19. Test songs with tempo changes.
20. Test songs with modulations.
21. Test multilingual lyrics where applicable.
22. Run regression tests whenever a transcription engine changes.

## Expected Results

- New transcription models can be evaluated objectively.
- Refactors do not silently degrade transcription.
- The project can compare fast vs high-quality pipelines.
- Generated scores are structurally valid.

## Acceptance Criteria

- CI contains deterministic tests for schema and score generation.
- At least one known melody has exact expected pitch/rhythm output within defined tolerance.
- MusicXML validation is automated.
- Benchmark reports can compare model versions.
