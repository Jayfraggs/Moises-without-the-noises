# Feature Plan 09 — Lyrics-to-Notes Alignment

## Motive

MWTN already uses Whisper for lyrics. To create a useful vocal score, lyrics must be synchronized not only to audio time but to musical note events and eventually MusicXML lyric syllables.

## Process

1. Preserve Whisper word/segment timestamps.
2. Improve timestamp resolution where possible.
3. Associate lyric words with vocal note events.
4. Split words into syllables when required for notation.
5. Determine syllable-to-note mapping.
6. Support melismas where one syllable spans multiple notes.
7. Support multiple syllables across one note only when musically justified.
8. Represent uncertain alignments explicitly.
9. Allow manual correction.
10. Generate lyric alignment data in the canonical project format.
11. Export aligned lyrics to MusicXML.
12. Synchronize lyric highlighting with playback and score position.
13. Keep original Whisper output separate from corrected alignment.

## Expected Results

- Vocal transcriptions can contain readable lyrics.
- Lyrics align with melody notes.
- MusicXML vocal scores can display lyrics.
- Alignment can be manually corrected without re-running transcription.

## Acceptance Criteria

- A simple vocal phrase aligns words/syllables to notes.
- Melismatic passages can be represented.
- Incorrect alignment can be corrected.
- Corrected alignment survives regeneration of unrelated artifacts.
