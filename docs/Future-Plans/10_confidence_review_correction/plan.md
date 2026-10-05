# Feature Plan 10 — Confidence, Error Detection and Human Review

## Motive

Automatic music transcription is inherently imperfect. A system that presents every prediction as fact will produce frustrating scores. MWTN should therefore make uncertainty visible and provide targeted correction tools.

## Process

1. Normalize confidence scores into a common [0,1] representation.
2. Attach confidence to:
   - notes
   - chords
   - lyrics alignment
   - key detection
   - tempo
   - beat/downbeat detection
3. Detect suspicious events:
   - extremely short notes
   - impossible overlaps
   - pitch jumps unlikely for the selected instrument
   - excessive polyphony
   - rhythm that does not fit the meter
   - conflicting chord/note evidence
4. Assign review severity.
5. Highlight uncertain notes in the UI.
6. Allow users to:
   - move notes
   - change pitch
   - change duration
   - delete notes
   - split notes
   - merge notes
   - change confidence/review status
7. Allow correction of chords and key.
8. Keep raw model output immutable.
9. Store user corrections as an overlay or edited layer.
10. Recompute downstream artifacts after corrections.
11. Do not require the user to rerun expensive source separation for simple musical edits.
12. Add an overall transcription quality indicator.
13. Provide an audit trail of corrections.

## Expected Results

- Users can quickly fix the mistakes that matter.
- The system is honest about uncertainty.
- Corrections survive regeneration.
- Human-edited scores can become better than raw model output.
- Future models can be evaluated against corrected data.

## Acceptance Criteria

- Low-confidence events are visually identifiable.
- Users can correct common pitch/rhythm errors.
- Corrections update score/solfa/MIDI outputs.
- Original model output remains recoverable.
