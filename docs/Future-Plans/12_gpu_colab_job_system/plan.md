# Feature Plan 12 — GPU/Colab Processing and Job Orchestration

## Motive

High-quality separation and AMT models can be computationally expensive. MWTN already has a Colab-oriented workflow. The expanded pipeline needs a formal job protocol so local and remote processing produce identical artifacts.

## Process

1. Define a versioned processing-job manifest.
2. A job should contain:
   - project ID
   - source hash
   - requested stems
   - separation model
   - transcription models
   - analysis options
   - output schema version
3. Define stages:
   - upload
   - separation
   - transcription
   - rhythm analysis
   - harmonic analysis
   - score generation
   - packaging
4. Give each stage a status and error state.
5. Make each stage resumable.
6. Use hashes to avoid recomputing existing artifacts.
7. Package outputs with a manifest.
8. Validate outputs before import into MWTN.
9. Keep temporary model files separate from final project artifacts.
10. Support local GPU execution and Colab execution using the same artifact contract.
11. Ensure remote processing never requires hidden assumptions about local filesystem paths.
12. Add compatibility checks for model/runtime versions.
13. Provide clear failure diagnostics.
14. Add optional resource estimates before starting expensive jobs.

## Expected Results

- A large song can be processed remotely without manual file shuffling.
- MWTN can import a completed processing package safely.
- Jobs can resume after interruption.
- Local and Colab results follow the same schema.

## Acceptance Criteria

- A complete job can be exported and imported.
- Interrupted jobs can resume from the last valid stage.
- Invalid/incomplete packages are rejected.
- Artifact metadata identifies the producing environment.
