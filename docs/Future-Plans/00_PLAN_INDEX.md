# MWTN Song-to-Score Expansion — Plan Index

These plans describe the expansion of **Moises without the Noises (MWTN)** from a stem-separation / music-analysis application into an integrated audio-to-musical-score workstation.

## Architectural Principle

The canonical source of truth is MWTN's versioned **MusicalEvent** representation.  
MuseScore, MIDI, MusicXML, solfa, chord charts, timelines, and all other views are **derived** from that representation — never the reverse.

## Intended End State

```
Audio → Separation → Stem-specific Transcription → Rhythm/Harmony Analysis
      → Canonical MusicalEvent Representation
      → Solfa + MIDI + MusicXML → MWTN Score UI / MuseScore
```

## Recommended Implementation Order

| # | Plan | Key Dependency |
|---|------|---------------|
| 1 | `01_architecture_and_contracts` | None — start here |
| 2 | `03_source_separation_pipeline` | Plan 01 schema |
| 3 | `12_gpu_colab_job_system` | Plan 01 + 03 |
| 4 | `02_transcription_engine` | Plan 01, 03, 12 |
| 5 | `04_rhythm_tempo_and_meter` | Plan 02 |
| 6 | `05_key_scale_chords` | Plan 02, 04 |
| 7 | `06_solfa_engine` | Plan 02, 05 |
| 8 | `07_musicxml_midi_export` | Plans 02–06 |
| 9 | `09_lyrics_alignment` | Plan 02, 07 |
| 10 | `10_confidence_review_correction` | Plan 02–07 |
| 11 | `11_score_ui` | Plans 07, 09, 10 |
| 12 | `08_musescore_integration` | Plan 07, 11 |
| 13 | `13_caching_performance_storage` | Pipeline stable |
| 14 | `14_testing_validation_benchmarking` | Run in parallel from Plan 01 |
| 15 | `15_security_reliability_packaging` | Pre-release hardening |
| 16 | `16_end_to_end_song_to_score` | All prior plans complete |

## Stack Constraints (Non-Negotiable)

- **No local model weights** — all heavy ML runs on Google Colab GPU
- **Open-source only** for all models and libraries
- **Offline-first** frontend — no CDN dependencies
- **Mobile-data aware** — flag any step with significant upload/download cost
- Backward-compatible with existing mwtn song data and `manifest.json` format
