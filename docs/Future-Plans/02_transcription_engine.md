# Plan 02 — Unified Automatic Music Transcription (AMT) Engine

## Motive

The existing mwtn note extraction uses **pYIN** (via librosa) — a monophonic pitch tracker. It works well for single-melody sources (solo vocals, bass) but cannot produce simultaneous notes. Piano, guitar, layered vocals, and most real-world instruments are polyphonic.

The expanded transcription system needs a **unified AMT layer** that dispatches different stems to the most appropriate transcription backend while always returning the same canonical `MusicalEvent` format defined in Plan 01.

---

## Open-Source AMT Model Options

All models below are open-source and Colab-compatible. This is the full current landscape — pick a profile or let the user configure per-stem.

---

### Option A — Basic Pitch (Spotify) ⭐ Recommended Default

| Property | Value |
|---|---|
| **License** | MIT |
| **Developer** | Spotify Research |
| **Install** | `pip install basic-pitch` |
| **Model size** | ~17 MB (NMP model weights) |
| **GPU support** | Yes (TensorFlow/Keras backend; also runs on CPU) |
| **Polyphonic** | Yes |
| **Instruments** | All (trained on mixed music, strongest on pitched instruments) |
| **Output** | MIDI + note events with onset/offset/pitch/confidence |
| **Colab data cost** | ~50 MB first install (deps); weights download automatically |
| **Strengths** | Fast, lightweight, good pitch accuracy, reliable onsets, handles vocals/piano/guitar/bass well |
| **Weaknesses** | Struggles with extreme polyphony (dense chords); not state-of-the-art for complex piano |

**Python usage:**
```python
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH

model_output, midi_data, note_events = predict(
    audio_path,
    ICASSP_2022_MODEL_PATH,
    onset_threshold=0.5,
    frame_threshold=0.3,
    minimum_note_length=58,   # ms
    minimum_frequency=32.7,   # Hz (C1)
    maximum_frequency=2093.0, # Hz (C7)
)
```

---

### Option B — MT3 (Google Magenta)

| Property | Value |
|---|---|
| **License** | Apache 2.0 |
| **Developer** | Google Brain / Magenta |
| **Install** | Complex — requires `t5x`, JAX, custom checkpoint |
| **Model size** | ~2 GB checkpoint |
| **GPU support** | JAX (TPU-native, GPU supported) |
| **Polyphonic** | Yes — multi-instrument |
| **Instruments** | 128 GM instruments |
| **Output** | MIDI token sequences |
| **Colab data cost** | ~2 GB checkpoint download per session |
| **Strengths** | Best open-source quality for multi-instrument transcription; handles full mixes |
| **Weaknesses** | Heavy setup, 2GB download, slower inference, JAX dependency |

> **Verdict:** Superior quality but impractical for the current Colab-first workflow. Treat as a **future high-quality option** behind a config flag. Do not implement in v1.

---

### Option C — Piano Transcription (Kong et al.)

| Property | Value |
|---|---|
| **License** | MIT |
| **Developer** | Qiuqiang Kong |
| **Install** | `pip install piano_transcription_inference` |
| **Model size** | ~150 MB |
| **GPU support** | Yes (PyTorch) |
| **Polyphonic** | Yes |
| **Instruments** | **Piano only** |
| **Output** | MIDI with pedal events |
| **Colab data cost** | ~200 MB total with deps |
| **Strengths** | Best open-source piano-specific transcription; includes sustain pedal |
| **Weaknesses** | Piano-only; no other instruments |

**Python usage:**
```python
from piano_transcription_inference import PianoTranscription, sample_rate, load_audio

transcriptor = PianoTranscription(device='cuda', checkpoint_path=None)
audio, _ = load_audio(audio_path, sr=sample_rate, mono=True)
transcribed_dict = transcriptor.transcribe(audio, midi_path)
```

> **Verdict:** Include as a **piano-stem specialization** activated when the piano stem is being transcribed and the user selects "high quality."

---

### Option D — Omnizart

| Property | Value |
|---|---|
| **License** | Custom (free for research/personal) |
| **Developer** | Music and Culture Technology Lab, Taiwan |
| **Install** | `pip install omnizart` |
| **Model size** | Multiple models ~50–500 MB each |
| **GPU support** | Yes (TensorFlow) |
| **Polyphonic** | Yes |
| **Instruments** | Piano, guitar, drum, chord, vocal, music (multi-instrument) |
| **Output** | MIDI |
| **Colab data cost** | Large first-run download per task |
| **Strengths** | Covers many instrument types including drums; active development |
| **Weaknesses** | Non-standard license (not fully OSI-approved); heavier install; less actively maintained than Basic Pitch |

> **Verdict:** Potentially useful for drum-specific transcription. License needs review before including in an open-source project. Treat as **optional / experimental**.

---

### Option E — Drum Transcription (ADTLib / DrumRoller)

| Property | Value |
|---|---|
| **License** | MIT (ADTLib) |
| **Developer** | Community |
| **Install** | `pip install adtlib` or from source |
| **Model size** | Small (<50 MB) |
| **Polyphonic** | N/A (multi-drum-voice) |
| **Instruments** | Drums only |
| **Output** | Note events per drum component (kick, snare, hi-hat, etc.) |
| **Strengths** | Purpose-built for drum stems |
| **Weaknesses** | Less well-maintained; output format needs normalization |

> **Verdict:** Include as a **drums-stem specialization** if Omnizart is excluded. Worth evaluating both.

---

### Option F — pYIN (existing, via librosa) — Keep as Lightweight Fallback

| Property | Value |
|---|---|
| **License** | ISC (librosa) |
| **Developer** | Librosa / orig. Mauch & Dixon |
| **Install** | Already installed |
| **Model size** | None (algorithmic) |
| **GPU support** | N/A |
| **Polyphonic** | **No — monophonic only** |
| **Instruments** | Any monophonic source (vocals, bass, single-line melody) |
| **Output** | Pitch track + note events |
| **Strengths** | Fast, zero download, works on CPU |
| **Weaknesses** | Cannot handle chords or simultaneous notes |

> **Verdict:** **Keep as the default for vocal and bass stems** where monophonic output is sufficient and speed matters. Activated automatically when the stem type is `vocals` or `bass` and the user selects "fast" mode.

---

## Transcription Profile Matrix

| Stem | Fast (default) | High Quality |
|---|---|---|
| `vocals` | pYIN | Basic Pitch |
| `bass` | pYIN | Basic Pitch |
| `piano` | Basic Pitch | Piano Transcription (Kong) |
| `guitar` | Basic Pitch | Basic Pitch (no better open-source option) |
| `drums` | ADTLib / Omnizart | ADTLib / Omnizart |
| `other` | Basic Pitch | Basic Pitch |

> **Guitar caveat:** Open-source guitar AMT quality is meaningfully lower than piano or vocal AMT. Outputs for guitar stems will require heavier human review (Plan 10). State this clearly in the UI.

---

## Process

### 1. Refactor existing note extraction
- Move `backend/note_extraction.py` into `backend/transcription/`
- Isolate pYIN logic into `backend/transcription/engines/pyin.py`

### 2. Define the engine interface
Every AMT engine implements:

```python
class AMTEngine(Protocol):
    def supports(self, stem_type: str, task: str) -> bool: ...
    def transcribe(self, audio_path: str, config: TranscriptionConfig) -> list[MusicalEvent]: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...
```

### 3. Implement engine adapters
```
backend/transcription/
  __init__.py
  dispatcher.py          # routes stems to engines by type + profile
  config.py              # TranscriptionConfig Pydantic model
  engines/
    __init__.py
    pyin.py              # existing monophonic engine (refactored)
    basic_pitch.py       # Basic Pitch adapter
    piano_kong.py        # Piano Transcription adapter (optional/high-quality)
    drums.py             # Drum transcription adapter (optional)
```

### 4. Preprocessing pipeline (per stem, before inference)
- Resample to model's required sample rate
- Convert to mono
- Loudness normalization (peak normalize to -1 dBFS)
- Silence trimming at boundaries
- Chunk long audio (>60s) with 2s overlapping windows
- Merge note events across chunk boundaries (deduplicate, merge overlapping)

### 5. Chunked inference
- Chunk size: 60 seconds
- Overlap: 2 seconds each side
- Merge strategy: prefer events from chunk center; drop duplicates within 20ms onset tolerance

### 6. Post-processing
- Apply minimum note duration filter (default: 50ms)
- Apply minimum confidence filter (default: 0.3)
- Remove impossible overlaps per voice
- Preserve expressive pitch information (do not quantize in this layer)

### 7. Output format
All engines return `list[MusicalEvent]` using the schema from Plan 01. Engine-specific raw output is cached separately and never exposed directly to the UI.

### 8. Async job integration
- Transcription runs as a background job
- Progress states: `queued → preprocessing → transcribing → merging → validating → complete | failed`
- Job status exposed via `GET /api/songs/{song_id}/transcription/{run_id}/status`

### 9. Caching
Cache key = `sha256(stem_audio) + model_name + model_version + config_hash`  
Cache location: `backend/data/<song_id>/transcription_cache/`

### 10. Configuration
Backend config file (`backend/transcription/config.yaml`) controls:
- Default engine per stem type
- Quality profile per stem type
- Confidence thresholds
- Chunk size / overlap
- Which optional engines are enabled

---

## Files to Create / Modify

```
backend/
  transcription/
    __init__.py
    dispatcher.py
    config.py
    engines/
      __init__.py
      pyin.py
      basic_pitch.py
      piano_kong.py      # optional, flag-gated
      drums.py           # optional, flag-gated
  transcription_config.yaml
```

Modify:
- `backend/main.py` — add transcription job endpoints
- `colab/mwtn_notebook.ipynb` — add Basic Pitch install cell + transcription cells

---

## Colab / Mobile Data Implications

| Action | Data Cost | When |
|---|---|---|
| `pip install basic-pitch` | ~50 MB | First Colab session only |
| Basic Pitch model weights | ~17 MB | First run, auto-downloaded |
| `pip install piano_transcription_inference` | ~200 MB | Only if piano high-quality selected |
| Piano Kong weights | ~150 MB | First run, auto-downloaded |
| ADTLib install | ~30 MB | Only if drums optional mode enabled |

All downloads happen on Colab. Zero local data cost.  
Per-song audio upload to Colab: ~3–10 MB (MP3). Output zip: ~30–80 MB.

---

## Expected Results

- A song can be transcribed without requiring one model to handle every instrument
- Vocals and bass remain fast (pYIN path unchanged)
- Piano produces simultaneous notes
- Guitar produces usable (if imperfect) polyphonic output with an honest quality warning
- Drum stems produce per-component events (kick, snare, hi-hat)
- Long recordings are chunked without memory issues
- All transcription results use the canonical MusicalEvent schema
- Users can choose Fast vs High Quality per stem

---

## Acceptance Criteria

- [ ] Vocal stem → ordered monophonic note events via pYIN
- [ ] Piano stem → simultaneous note events via Basic Pitch
- [ ] Long audio (>5 min) processes in chunks without crashing
- [ ] Identical re-run uses cached results
- [ ] Every result includes `source_model`, `confidence`, `schema_version`
- [ ] Failed jobs return structured errors, not partial/silent data
- [ ] pYIN path continues to work as before
- [ ] Engine can be selected per stem in `transcription_config.yaml`
