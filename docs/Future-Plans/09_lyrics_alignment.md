# Plan 09 — Lyrics-to-Notes Alignment

## Motive

MWTN already uses OpenAI Whisper for word-level lyric transcription with timestamps. However, Whisper timestamps are aligned to **audio time**, not to **musical note events**. To create a useful vocal score, lyrics must be synchronized to the note events produced by the transcription engine (Plan 02) and eventually embedded as MusicXML lyric syllables (Plan 07).

---

## Current State

- Whisper produces `lyrics.json` with word-level timestamps: `[{ "word": "hello", "start": 1.24, "end": 1.61 }, ...]`
- These are used for karaoke sync in the frontend
- No connection exists yet between lyric timestamps and note events

---

## Process

### 1. Preserve existing Whisper output as the source of record
- `lyrics.json` is never modified by the alignment pipeline
- All alignment data is stored in a separate `lyrics_alignment.json`
- The original Whisper timestamps remain the authoritative source

### 2. Improve Whisper timestamp resolution (optional)
Standard Whisper (`base` or `small` model) word timestamps can have ±100ms error.

**Option: WhisperX** — forced alignment using phoneme-level aligner (wav2vec2)
```bash
pip install whisperx
```
- MIT-style license
- Produces character/phoneme-level timestamps, significantly more accurate
- Requires `torch`, `torchaudio` (already available on Colab)
- Data cost: ~400 MB (wav2vec2 alignment model, downloaded once per Colab session)

**Decision:** Make WhisperX an optional enhancement behind a `use_whisperx: true` config flag. Default remains standard Whisper (already installed).

### 3. Associate lyric words with vocal note events
For each word in the Whisper output:
1. Find all `NoteEvent` objects on the `vocals` stem where the note's time range overlaps with the word's time range
2. Assign the word to the note(s) it overlaps with

```python
def align_word_to_notes(
    word: WhisperWord,
    note_events: list[NoteEvent],
    tolerance_s: float = 0.1
) -> list[NoteEvent]:
    matching_notes = [
        n for n in note_events
        if n.start_time < word.end + tolerance_s
        and n.end_time > word.start - tolerance_s
    ]
    return matching_notes
```

### 4. Syllable splitting
For notation, words must be split into syllables (one syllable per note in melismatic passages).

Use **pyphen** for hyphenation/syllabification:
```bash
pip install pyphen
```
- LGPL license
- Supports: English, Spanish, Portuguese, French, Italian (matching Whisper's supported languages for MWTN)
- Usage:
  ```python
  import pyphen
  dic = pyphen.Pyphen(lang='en_US')
  syllables = dic.inserted('singing')  # → 'sing-ing'
  ```

### 5. Syllable-to-note mapping

A syllable-to-note assignment can be:
- **1:1** — one syllable, one note (most common)
- **melisma** — one syllable across multiple notes (mark the first note, use extender lines in MusicXML)
- **elision** — multiple syllables on one note (only when justified by note length; rare)

```json
{
  "word": "singing",
  "syllables": [
    { "text": "sing", "note_ids": ["note_001"], "type": "1:1" },
    { "text": "ing",  "note_ids": ["note_002", "note_003"], "type": "melisma" }
  ]
}
```

### 6. Represent uncertain alignments explicitly
When no note event clearly corresponds to a lyric word (gap in transcription, low note confidence):
```json
{
  "word": "hello",
  "alignment_confidence": 0.41,
  "alignment_status": "uncertain",
  "note_ids": []
}
```

### 7. Manual correction
- The UI (Plan 11) exposes lyric alignment corrections
- Users can drag a lyric syllable to a different note
- Corrections stored as a corrections overlay (Plan 10 pattern)
- Corrected alignment survives regeneration of unrelated artifacts

### 8. Canonical alignment format

File: `backend/data/<song_id>/lyrics_alignment.json`

```json
{
  "schema_version": "1.0",
  "source_lyrics_run": "<whisper_run_id>",
  "source_transcription_run": "<amt_run_id>",
  "language": "en",
  "syllabifier": "pyphen_en_US",
  "words": [
    {
      "word_index": 0,
      "word": "sing",
      "whisper_start": 0.84,
      "whisper_end": 1.12,
      "syllables": [
        {
          "syllable_index": 0,
          "text": "sing",
          "note_ids": ["note_042"],
          "alignment_type": "1:1",
          "alignment_confidence": 0.92,
          "manually_corrected": false
        }
      ]
    }
  ]
}
```

### 9. MusicXML lyric export
Pass alignment data to Plan 07 (MusicXML export):
- music21 `Lyric` objects are attached to the corresponding `Note` objects
- Melismas use `lyricConnector` to extend across multiple notes

### 10. Playback sync
The existing karaoke word-highlight logic uses raw Whisper timestamps.  
After alignment is complete, the frontend can optionally switch to note-aligned highlighting — more precise but only available for transcribed stems.

---

## Files to Create / Modify

```
backend/
  lyrics/
    __init__.py
    alignment.py      # word-to-note alignment engine
    syllabifier.py    # pyphen wrapper; multi-language support
    whisperx.py       # optional WhisperX enhanced alignment
```

Modify:
- `backend/main.py` — add lyrics alignment endpoint
- `colab/mwtn_notebook.ipynb` — add pyphen install cell; optional WhisperX cell
- `backend/export/musicxml_exporter.py` — consume alignment data for lyrics

---

## Colab / Mobile Data Implications

| Action | Data Cost | Notes |
|---|---|---|
| `pip install pyphen` | ~5 MB | Very lightweight |
| `pip install whisperx` | ~50 MB | Optional; enhanced alignment only |
| wav2vec2 alignment model | ~400 MB | Optional; WhisperX only; cached per Colab session |

Standard workflow (pyphen only): **~5 MB extra**. WhisperX path is opt-in and flagged clearly.

---

## Expected Results

- Vocal transcriptions can contain readable, correctly positioned lyrics
- Lyrics align with melody notes well enough for notation
- MusicXML vocal scores display lyrics under the correct notes
- Melismatic passages are representable
- Alignment can be manually corrected without re-running transcription

---

## Acceptance Criteria

- [ ] A simple English vocal phrase aligns words to notes correctly
- [ ] Melismatic passages (one syllable across multiple notes) are represented
- [ ] Multi-syllable words are split correctly via pyphen
- [ ] Alignment confidence is recorded per syllable
- [ ] Uncertain alignments are explicitly flagged (not silently assigned)
- [ ] Manual corrections survive regeneration of unrelated artifacts
- [ ] Aligned lyrics appear correctly in generated MusicXML
- [ ] Original Whisper output is never modified
