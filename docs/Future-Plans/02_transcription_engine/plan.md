# Feature Plan 02 — Unified Automatic Music Transcription Engine

## Motive

The existing MWTN note extraction is primarily oriented toward monophonic pitch tracking. That is useful for vocals and bass, but it is insufficient for complete musical transcription because piano, guitar, layered vocals, and other instruments can contain multiple simultaneous notes.

The project needs a unified transcription layer that can dispatch different stems to appropriate transcription methods while returning the same canonical musical-event format.

## Process

1. Refactor the existing note extraction implementation into a transcription subsystem.
2. Separate transcription into capabilities rather than one universal model:
   - monophonic melody transcription
   - bass transcription
   - polyphonic piano transcription
   - polyphonic guitar transcription
   - drum transcription
   - vocal melody transcription
3. Keep model selection configurable through a backend configuration file.
4. Implement an engine interface conceptually similar to:
   - `supports(stem_type, task)`
   - `transcribe(audio, config)`
   - `health_check()`
   - `model_info()`
5. Preserve the existing pYIN path as a lightweight/fast backend for suitable monophonic sources.
6. Add a higher-quality AMT backend for polyphonic material.
7. Make model dependencies optional so the basic application remains installable without every heavyweight model.
8. Implement preprocessing per stem:
   - resampling
   - loudness normalization where appropriate
   - silence trimming
   - optional denoising
   - channel conversion
   - chunking for long recordings
9. Implement chunked inference for long songs.
10. Add overlap between chunks to reduce boundary errors.
11. Merge overlapping note events.
12. Remove duplicate detections.
13. Apply minimum note-duration filtering.
14. Preserve expressive pitch information where useful rather than quantizing too early.
15. Generate confidence scores for every note whenever the selected model supports them.
16. Record model/version/configuration in the transcription metadata.
17. Expose transcription as an asynchronous backend job.
18. Add job progress states:
   - queued
   - preprocessing
   - transcribing
   - merging
   - validating
   - complete
   - failed
19. Cache transcription results using a hash of:
   - source audio/stem
   - model
   - model version
   - configuration
20. Add deterministic reprocessing options.

## Expected Results

- A song can be transcribed without requiring one model to handle every instrument.
- Vocal and bass transcription remain fast.
- Piano/guitar can produce simultaneous notes.
- Long recordings can be processed without exhausting memory.
- Transcription results use the canonical musical-event schema.
- Users can choose between faster and higher-quality transcription modes.
- Existing MWTN note extraction remains available as a lightweight option.

## Acceptance Criteria

- A vocal stem produces ordered note events.
- A polyphonic test file produces simultaneous notes where appropriate.
- Long audio can be processed in chunks.
- Re-running an identical transcription can use cached results.
- Every transcription result contains model and configuration metadata.
- Failed jobs return useful errors instead of silently producing partial data.
