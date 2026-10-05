# Feature Plan 03 — Production Source-Separation Pipeline

## Motive

Reliable transcription depends heavily on the quality of the audio supplied to each transcription model. MWTN already supports source separation, but the expanded transcription system needs a formal separation pipeline capable of producing task-specific stems and recording exactly how they were generated.

## Process

1. Audit the existing Demucs/separation implementation and all supported separation modes.
2. Create a common separation-engine interface.
3. Support configurable engines/models rather than hard-coding one implementation.
4. Define standard stem roles:
   - vocals
   - drums
   - bass
   - guitar
   - piano
   - other
5. Support fallback mappings when an engine does not provide all requested stems.
6. Store model name/version and separation configuration in the project manifest.
7. Normalize output naming and directory structure.
8. Preserve original audio separately from derived stems.
9. Add stem validation:
   - file exists
   - duration matches source within tolerance
   - sample rate is known
   - channels are valid
   - file is readable
10. Add optional preprocessing specifically for transcription.
11. Allow users to choose:
   - fast separation
   - high-quality separation
   - minimum requested stems
   - full transcription-oriented stem set
12. Cache separation results using source hash + engine/model/configuration.
13. Expose separation as a job with progress reporting.
14. Ensure a failed stem does not silently masquerade as a successful stem.
15. Make the pipeline capable of running locally or through the existing Colab/GPU workflow.
16. Define how separated stems are transferred back into the main project.
17. Keep raw stems and processed transcription audio distinct.

## Expected Results

- Every transcription run starts from validated, traceable stems.
- Users can select a quality/performance profile.
- Separation outputs are reusable across multiple analyses.
- MWTN can use different separation engines in the future.
- The backend can determine exactly which stem produced each transcription result.

## Acceptance Criteria

- A source song produces validated standard stems.
- Stem generation is resumable/cached.
- Manifest records the exact separation configuration.
- Missing/failed stems are clearly reported.
- Existing MWTN separation workflows continue to work.
