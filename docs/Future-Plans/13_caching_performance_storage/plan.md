# Feature Plan 13 — Artifact Caching, Performance and Storage Management

## Motive

Separation and transcription are expensive. Recomputing them every time the user changes a display option or exports another format would make MWTN unnecessarily slow and GPU-heavy.

## Process

1. Hash source audio.
2. Hash relevant processing configuration.
3. Use composite cache keys for:
   - separation
   - transcription
   - beat tracking
   - harmonic analysis
   - score generation
4. Cache immutable intermediate artifacts.
5. Store generated artifacts in predictable project directories.
6. Separate cache from user-owned project data.
7. Add cache invalidation based on schema/model/configuration changes.
8. Avoid recomputing solfa when only the UI changes.
9. Avoid recomputing MusicXML when only MIDI export is requested if the underlying score model is unchanged.
10. Add disk-space reporting.
11. Allow deletion of derived artifacts while preserving source audio.
12. Support optional compression for large JSON/intermediate files.
13. Prevent concurrent jobs from corrupting shared artifacts.

## Expected Results

- Repeated operations become substantially faster.
- GPU use is reduced.
- Users can safely regenerate outputs.
- Storage remains understandable and manageable.

## Acceptance Criteria

- Identical jobs reuse cached results.
- Changed model/configuration produces a new artifact.
- Cache invalidation does not delete source audio.
- Concurrent jobs do not overwrite each other's output.
