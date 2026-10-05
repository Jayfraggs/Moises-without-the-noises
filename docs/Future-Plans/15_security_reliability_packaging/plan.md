# Feature Plan 15 — Reliability, Security and Distribution

## Motive

The expanded system will execute external model code, process arbitrary audio, create files, and potentially launch external applications such as MuseScore. These operations need controlled boundaries.

## Process

1. Validate uploaded file types.
2. Limit file sizes and processing durations where appropriate.
3. Sanitize project/song identifiers used in paths.
4. Prevent path traversal through uploaded filenames.
5. Run external model processes without unsafe shell interpolation.
6. Capture stdout/stderr safely.
7. Apply timeouts to child processes.
8. Clean temporary files after failed jobs.
9. Ensure generated artifacts cannot overwrite arbitrary filesystem locations.
10. Validate MusicXML before export/open operations.
11. Treat model files as trusted installation dependencies rather than arbitrary user executables.
12. Record processing errors in structured logs.
13. Add health checks for:
    - backend
    - model availability
    - FFmpeg
    - separation engine
    - transcription engine
    - MuseScore detection
14. Make heavyweight dependencies optional by feature.
15. Document CPU-only and GPU-capable installation modes.
16. Package the desktop build with sensible defaults.
17. Provide clear setup instructions for optional models.
18. Keep licensing information for all third-party models and libraries.

## Expected Results

- Arbitrary audio cannot easily break the processing pipeline.
- External processes are controlled.
- Desktop and local deployments remain maintainable.
- Users know which optional components they need.
- The project can be distributed without accidentally bundling incompatible model assets.

## Acceptance Criteria

- Malicious/invalid paths are rejected.
- Failed child processes are cleaned up.
- Health checks expose missing dependencies.
- Installation documentation covers all transcription features.
- Third-party licenses are documented.
