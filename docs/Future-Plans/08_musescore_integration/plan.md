# Feature Plan 08 — MuseScore Integration

## Motive

MuseScore should serve as MWTN's high-quality notation and score-editing backend/frontend rather than duplicating a full notation engine inside MWTN.

The safest first integration is file-based: generate MusicXML/MIDI and open it in an installed MuseScore application. Deeper integration can follow later.

## Process

1. Detect whether MuseScore is installed.
2. Support configurable MuseScore executable paths.
3. Support Windows/Linux/macOS where feasible.
4. Generate MusicXML into a temporary or project-specific score directory.
5. Add a frontend action such as `Open in MuseScore`.
6. Launch MuseScore with the generated score.
7. Add `Export MusicXML` and `Export MIDI` independently.
8. Preserve a copy of the generated score inside the MWTN project.
9. Record which MWTN transcription run produced the score.
10. Add optional round-trip support later:
    - MWTN generates MusicXML
    - user edits in MuseScore
    - user saves
    - MWTN can import the edited MusicXML
11. Clearly distinguish:
    - generated score
    - user-edited score
12. Never overwrite a user-edited score automatically.
13. Provide score regeneration as a new version.
14. Later evaluate deeper MuseScore plugin/API integration only after the file-based workflow is stable.

## Expected Results

- Users can press one button to turn a transcription into an editable MuseScore document.
- MWTN remains independent of MuseScore's internal C++ architecture.
- MuseScore acts as a professional engraving/editor environment.
- Future score editors can be supported through MusicXML.

## Acceptance Criteria

- Installed MuseScore can be detected.
- Generated MusicXML can be opened directly.
- User-edited scores are not overwritten by automatic regeneration.
- Export works even when MuseScore is not installed.
