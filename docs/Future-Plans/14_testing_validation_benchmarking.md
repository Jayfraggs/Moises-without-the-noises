# Plan 14 — Automated Testing, Musical Validation and Benchmarking

## Motive

Audio transcription can fail in subtle musical ways while still producing technically valid files. A piano transcription that shifts every note up a semitone passes JSON schema validation and produces valid MusicXML — but is musically wrong. MWTN needs a **test corpus and musical validation framework** that goes beyond conventional unit tests.

This plan runs in parallel with all others from Plan 01 onward — every implemented feature should have tests added in the same implementation wave, not after.

---

## Test Categories

### 1. Unit Tests (pytest)
Pure Python logic — no audio, no models.

```
tests/
  unit/
    test_schema.py             # MusicalEvent validation, schema migration
    test_solfa_engine.py       # pitch → scale degree → syllable logic
    test_quantizer.py          # duration normalization, tie generation
    test_cache_keys.py         # cache key determinism
    test_enharmonic_spelling.py
    test_correction_overlay.py # correction apply + undo
    test_manifest.py           # manifest read/write/migrate
```

### 2. Integration Tests (pytest + test audio)
Real audio processing with small synthetic test files.

```
tests/
  integration/
    test_separation_pipeline.py
    test_transcription_basic_pitch.py
    test_transcription_pyin.py
    test_beat_tracker.py
    test_key_detection.py
    test_chord_detection.py
    test_lyrics_alignment.py
    test_musicxml_export.py
    test_midi_export.py
    test_solfa_pipeline.py    # end-to-end from audio → solfa
    test_api_endpoints.py     # FastAPI test client
```

### 3. Musical Validation Tests (pytest + known ground truth)
Tests with known correct musical answers.

### 4. MusicXML Structural Validation
Automated rendering checks using MuseScore CLI.

### 5. Benchmark Tests
Performance regression detection.

---

## Synthetic Test Audio

Generated programmatically — no licensing issues, deterministic, reproducible.

### Test set A — Simple melodic inputs (monophonic)

```python
import numpy as np
import soundfile as sf

def generate_sine_note(freq_hz: float, duration_s: float, sr: int = 22050) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq_hz * t)

# C major scale, quarter notes at 120 BPM (0.5s each)
C_MAJOR_FREQS = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]
scale_audio = np.concatenate([generate_sine_note(f, 0.5) for f in C_MAJOR_FREQS])
sf.write("tests/fixtures/c_major_scale.wav", scale_audio, 22050)
```

### Test set B — Simple melodic inputs with known solfa

| File | Pitches | Key | Expected solfa |
|---|---|---|---|
| `c_major_scale.wav` | C D E F G A B C | C major | Do Re Mi Fa Sol La Ti Do |
| `g_major_scale.wav` | G A B C D E F# G | G major | Do Re Mi Fa Sol La Ti Do |
| `a_minor_scale.wav` | A B C D E F G A | A minor | La Ti Do Re Mi Fa Sol La |
| `simple_melody.wav` | C E G E C | C major | Do Mi Sol Mi Do |

### Test set C — Rhythmic inputs

| File | Content | Expected |
|---|---|---|
| `quarter_notes_120bpm.wav` | 4 quarter notes at 120 BPM | 4 quarter notes, measure = 4/4 |
| `mixed_durations.wav` | quarter + eighth + half | correct duration mix |
| `cross_barline.wav` | note crossing bar 1 → bar 2 | two tied notes |

### Test set D — Polyphonic inputs (for Basic Pitch)

| File | Content | Expected |
|---|---|---|
| `major_triad.wav` | C + E + G simultaneous | 3 simultaneous notes |
| `alberti_bass.wav` | C-G-E-G pattern | 4 sequential notes |

### Test set E — Edge cases

| File | Content | Purpose |
|---|---|---|
| `silence.wav` | 5s of silence | No notes generated; no crash |
| `noise.wav` | White noise | Graceful low-confidence output |
| `long_audio.wav` | 6 minutes, simple melody | Chunking works correctly |
| `tempo_change.wav` | 120 BPM → 140 BPM midway | Tempo map captures change |

---

## Ground Truth Format

```json
{
  "file": "c_major_scale.wav",
  "expected_notes": [
    { "midi_pitch": 60, "start_beat": 1.0, "duration_beats": 1.0 },
    { "midi_pitch": 62, "start_beat": 2.0, "duration_beats": 1.0 },
    ...
  ],
  "expected_key": { "tonic": "C", "mode": "major" },
  "expected_tempo": 120.0,
  "expected_solfa": ["Do", "Re", "Mi", "Fa", "Sol", "La", "Ti", "Do"]
}
```

---

## Musical Accuracy Metrics

### Note-level metrics (frame-level evaluation)
Using **mir_eval** (MIT license):
```bash
pip install mir_eval
```

| Metric | What it measures |
|---|---|
| Note F1 | Precision + recall on onset + pitch pairs |
| Onset accuracy | ±50ms tolerance |
| Offset accuracy | ±50ms or 20% of note duration |
| Pitch accuracy | Exact MIDI pitch match |

```python
import mir_eval

ref_intervals = np.array([[note.start_time, note.end_time] for note in ground_truth])
ref_pitches   = np.array([note.midi_pitch for note in ground_truth])
est_intervals = np.array([[note.start_time, note.end_time] for note in predicted])
est_pitches   = np.array([note.midi_pitch for note in predicted])

precision, recall, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
    ref_intervals, ref_pitches,
    est_intervals, est_pitches,
    onset_tolerance=0.05,
    pitch_tolerance=0.25
)
```

### Chord accuracy
```python
chord_acc = mir_eval.chord.weighted_accuracy(ref_labels, ref_intervals, est_labels, est_intervals)
```

### Key detection accuracy
Simple exact match (tonic + mode) with enharmonic equivalence:
```python
is_correct = (predicted_tonic_pc == ref_tonic_pc) and (predicted_mode == ref_mode)
```

### Solfa accuracy
After alignment: percentage of syllables that match ground truth.

### Lyric alignment error
Mean absolute time difference between predicted and reference word boundaries (milliseconds).

---

## MusicXML Structural Validation

After every MusicXML generation:

1. **Schema validation via music21:**
```python
import music21 as m21
score = m21.converter.parse(xml_path)
score.isWellFormedNotation()  # returns bool
```

2. **MuseScore CLI headless render (if MuseScore installed):**
```bash
mscore -o /tmp/test_output.pdf tests/fixtures/generated.xml
# Exit code 0 = valid; non-zero = structural error
```

3. **Check measure totals:**
```python
for part in score.parts:
    for measure in part.getElementsByClass('Measure'):
        assert measure.duration.quarterLength == time_sig.barDuration.quarterLength
```

---

## Benchmark Tests

Track these metrics across model/code changes:

| Benchmark | Target | Regression threshold |
|---|---|---|
| pYIN transcription (30s mono) | < 2s | > 5s |
| Basic Pitch transcription (30s mono) | < 10s | > 20s |
| Beat tracking (3min song) | < 5s | > 15s |
| Key detection (3min song) | < 1s | > 3s |
| MusicXML generation (simple song) | < 2s | > 5s |
| API response (manifest) | < 50ms | > 200ms |

Benchmarks are run separately from the main test suite (opt-in via `pytest -m benchmark`).

---

## CI Integration

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r backend/requirements-dev.txt
      - run: pytest tests/unit/ -v
      - run: pytest tests/integration/ -v --timeout=120
```

Colab-dependent tests (actual Demucs separation, large AMT models) are excluded from CI and run manually or on a self-hosted GPU runner.

---

## Files to Create

```
tests/
  fixtures/
    generate_fixtures.py     # synthetic audio generation script
    ground_truth/
      c_major_scale.json
      simple_melody.json
      ...
  unit/
    test_schema.py
    test_solfa_engine.py
    test_quantizer.py
    test_cache_keys.py
    test_correction_overlay.py
    test_enharmonic_spelling.py
  integration/
    test_transcription_basic_pitch.py
    test_transcription_pyin.py
    test_beat_tracker.py
    test_musicxml_export.py
    test_solfa_pipeline.py
    test_api_endpoints.py
  musical/
    test_ground_truth.py     # known input → known output tests
    test_musicxml_valid.py   # structural validation
  conftest.py                # shared fixtures
  requirements-test.txt      # mir_eval, pytest, pytest-asyncio, httpx
```

---

## Colab / Mobile Data Implications

Unit and integration tests run locally — no Colab, no network. Only the GPU-dependent tests (full Demucs separation, large AMT models) require Colab.

`pip install mir_eval` is a test-only dependency (~5 MB). Not included in the production backend requirements.

---

## Expected Results

- New AMT models can be objectively compared against existing ones using mir_eval metrics
- Refactors cannot silently degrade transcription quality (regression tests catch it)
- The project can compare Fast vs High Quality pipeline outputs quantitatively
- Generated MusicXML is structurally validated automatically on every generation

---

## Acceptance Criteria

- [ ] CI runs unit + integration tests on every push without requiring a GPU
- [ ] `c_major_scale.wav` → solfa output is `Do Re Mi Fa Sol La Ti Do` (exact match)
- [ ] Basic Pitch on `major_triad.wav` produces 3 simultaneous notes within ±1 semitone
- [ ] `silence.wav` produces 0 note events and no crash
- [ ] `long_audio.wav` processes in chunks without memory error
- [ ] All generated MusicXML passes music21 well-formedness check
- [ ] Benchmark results are recorded and compared against baselines
