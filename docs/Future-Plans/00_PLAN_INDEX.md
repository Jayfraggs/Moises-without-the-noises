# MWTN Musical Transcription Expansion — Plan Index

These plans describe the proposed expansion of **Moises without the Noises (MWTN)** from a stem-separation/music-analysis application into an integrated audio-to-musical-score workstation.

## Recommended implementation order

1. `01_project_architecture_and_contracts`
2. `03_source_separation_pipeline`
3. `02_transcription_engine`
4. `04_rhythm_tempo_and_meter`
5. `05_key_scale_chords`
6. `06_solfa_engine`
7. `07_musicxml_midi_export`
8. `09_lyrics_alignment`
9. `10_confidence_review_correction`
10. `12_gpu_colab_job_system`
11. `13_caching_performance_storage`
12. `11_score_ui`
13. `08_musescore_integration`
14. `14_testing_validation_benchmarking`
15. `15_security_reliability_packaging`
16. `16_end_to_end_song_to_score`

## Architectural principle

The canonical source of truth should be MWTN's versioned musical-event representation.

MuseScore, MIDI, MusicXML, solfa, chord charts, timelines, and other views should be derived from that representation rather than becoming separate competing representations.

## Intended end state

`Audio → Separation → Stem-specific transcription → Rhythm/harmony analysis → Canonical musical representation → Solfa + MIDI + MusicXML → MWTN Score UI / MuseScore`

The plans intentionally separate concerns so each feature can be implemented, tested, and replaced independently.
