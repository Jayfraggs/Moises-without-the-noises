# Feature Plan 01 — Musical Intelligence Architecture and Data Contracts

## Motive

MWTN already performs audio separation and several forms of analysis. The next major capability is to turn those independent analysis outputs into a coherent musical representation that can feed notation, MIDI, solfa, chord analysis, and future editing features.

The project should not make MuseScore, MIDI, MusicXML, solfa, or any individual transcription model the canonical source of truth. The canonical representation should be a model-independent collection of musical events and metadata. Every output format should be derived from that representation.

This prevents the system from becoming tightly coupled to one transcription model and allows better models to be introduced later without rewriting the frontend or score-generation layer.

## Process

1. Audit the current backend data flow, existing `manifest.json`/song metadata, separation output, note extraction output, lyrics output, BPM output, and key detection output.
2. Define a versioned musical project schema.
3. Define stable identifiers for songs, stems, tracks, notes, chords, sections, beats, and transcription runs.
4. Define a `MusicalEvent` model containing at minimum:
   - event ID
   - track/stem ID
   - event type
   - start time in seconds
   - end time or duration
   - MIDI pitch when applicable
   - velocity/confidence when available
   - source model
   - transcription confidence
   - optional quantized position
5. Define separate representations for:
   - note events
   - rests
   - chord events
   - drum hits
   - lyric words/syllables
   - beat/downbeat events
   - key/scale information
   - tempo/time-signature information
   - musical sections
6. Define a project-level manifest describing:
   - source audio
   - source hash
   - separation engine/version
   - transcription engine/version
   - analysis settings
   - generated artifacts
   - schema version
   - timestamps
   - confidence/quality information
7. Define an artifact registry so generated MIDI, MusicXML, JSON, lyrics alignment, solfa, and analysis files can be regenerated independently.
8. Preserve backward compatibility with existing MWTN song data where practical.
9. Add schema validation at API boundaries.
10. Establish explicit units:
    - audio time in seconds
    - MIDI pitch as integer 0–127
    - frequency in Hz
    - tempo in BPM
    - confidence in [0, 1]
    - musical positions using a clearly defined PPQ/tick convention where needed.
11. Add schema versioning and migration utilities.
12. Document which fields are authoritative and which are derived.

## Expected Results

- MWTN has one canonical internal musical representation.
- Existing features can continue operating.
- Future transcription models can be swapped without changing the UI contract.
- MIDI, MusicXML, solfa, chord charts, tabs, and visual timelines can all be generated from the same source.
- Every generated result can be traced back to its model/configuration.
- The system can detect stale artifacts and regenerate them when source data changes.
- Data contracts are explicit enough for both human developers and AI coding agents to work safely.

## Acceptance Criteria

- A representative song can be represented entirely by the new schema.
- Existing songs can be loaded without losing existing analysis data.
- Schema validation rejects malformed musical events.
- Schema version is recorded in every project/manifest.
- At least one existing note-extraction result can be converted into the new event representation.
- A generated artifact records its source run and configuration.
