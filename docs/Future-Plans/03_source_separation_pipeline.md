# Plan 03 — Production Source-Separation Pipeline

## Motive

Reliable transcription depends heavily on the quality of audio supplied to each AMT model. MWTN already supports source separation via Demucs, but the expanded transcription system needs a **formal separation pipeline** that records exactly how stems were generated, supports different quality profiles, and validates outputs before passing them downstream.

---

## Open-Source Separation Model Options

All models run on Colab GPU. All are open-source.

---

### Option A — Demucs htdemucs_6s ⭐ Current / Recommended Default

| Property | Value |
|---|---|
| **License** | MIT |
| **Developer** | Meta AI Research |
| **Stems** | 6: vocals, bass, drums, guitar, piano, other |
| **Model size** | ~80 MB |
| **Quality** | High — state-of-the-art for 6-stem separation |
| **Speed** | ~2–4× real-time on Colab GPU |
| **Install** | `pip install demucs` |

> **Verdict:** Keep as primary engine. Already integrated.

---

### Option B — Demucs htdemucs (4-stem)

| Property | Value |
|---|---|
| **License** | MIT |
| **Stems** | 4: vocals, bass, drums, other |
| **Model size** | ~80 MB |
| **Quality** | Comparable to 6s; slightly faster |
| **Use case** | When piano/guitar stems are not needed |

> **Verdict:** Offer as "fast" profile when only vocal/bass/drums are requested.

---

### Option C — Demucs mdx_extra (MDX-Net variant)

| Property | Value |
|---|---|
| **License** | MIT |
| **Stems** | 4: vocals, bass, drums, other |
| **Model size** | ~83 MB |
| **Quality** | Slightly better vocal isolation in some benchmarks |
| **Notes** | MDX challenge winner variant |

> **Verdict:** Offer as an alternative for vocal-focused workflows (karaoke, lyric transcription).

---

### Option D — Spleeter (Deezer)

| Property | Value |
|---|---|
| **License** | MIT |
| **Developer** | Deezer Research |
| **Stems** | 2-stem (vocal/accompaniment), 4-stem, or 5-stem |
| **Model size** | ~100–150 MB per config |
| **Speed** | Fast — faster than Demucs on CPU |
| **Quality** | Lower than Demucs htdemucs_6s |
| **Install** | `pip install spleeter` |

> **Verdict:** Include as a **legacy/fast fallback** for CPU-only environments where Demucs is too slow. Not recommended for transcription quality.

---

### Option E — Open-Unmix (UMX)

| Property | Value |
|---|---|
| **License** | MIT |
| **Developer** | Fabian-Robert Stöter / Inria |
| **Stems** | 4: vocals, bass, drums, other |
| **Model size** | ~70 MB |
| **Quality** | Good; slightly below Demucs in recent benchmarks |
| **Install** | `pip install openunmix` |

> **Verdict:** Alternative to Spleeter as a fallback. Better quality than Spleeter, comparable speed to Demucs.

---

### Option F — Demucs bag-of-models (ensemble)

| Property | Value |
|---|---|
| **License** | MIT |
| **Stems** | 4 or 6 depending on ensemble |
| **Quality** | Best quality; averages multiple model outputs |
| **Speed** | ~3–5× slower than single model |
| **Colab data cost** | ~300–500 MB (multiple checkpoints) |

> **Verdict:** Offer as **"maximum quality"** profile. Flag the significant data cost to users before activation.

---

## Separation Profile Matrix

| Profile | Engine | Stems | Colab Cost | Use Case |
|---|---|---|---|---|
| `fast` | htdemucs (4s) | vocals, bass, drums, other | ~80 MB | Quick preview, lyric practice |
| `standard` (default) | htdemucs_6s | all 6 | ~80 MB | Full transcription workflow |
| `vocal_focus` | mdx_extra | vocals + others | ~83 MB | Karaoke, lyric alignment |
| `max_quality` | bag-of-models ensemble | all 6 | ~400 MB | Final score production |
| `cpu_only` | Spleeter 4-stem | 4 | ~120 MB | Local CPU fallback |

---

## Process

### 1. Audit existing separation implementation
- Review `backend/separation.py` and all Colab notebook separation cells
- Document all currently hard-coded assumptions (model name, output path, stem naming)

### 2. Create a common separation engine interface

```python
class SeparationEngine(Protocol):
    def supports_stems(self) -> list[str]: ...
    def separate(self, audio_path: str, config: SeparationConfig) -> SeparationResult: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...
```

### 3. Define standard stem roles
```
vocals, drums, bass, guitar, piano, other
```

Fallback mappings when an engine doesn't provide a requested stem:
- `guitar` not available → map to `other`
- `piano` not available → map to `other`

### 4. Store separation metadata in the manifest
```json
{
  "separation": {
    "engine": "demucs",
    "model": "htdemucs_6s",
    "version": "4.0.1",
    "profile": "standard",
    "source_hash": "<sha256>",
    "stems_produced": ["vocals", "bass", "drums", "guitar", "piano", "other"],
    "config": {},
    "completed_at": "<ISO8601>"
  }
}
```

### 5. Normalize output naming and directory structure
All stems written to: `backend/data/<song_id>/stems/<stem_name>.wav`  
Original audio preserved at: `backend/data/<song_id>/source/original.<ext>`

### 6. Stem validation (run after every separation)
For each expected stem:
- [ ] File exists at expected path
- [ ] Duration matches source ± 500ms tolerance
- [ ] Sample rate is known and recorded
- [ ] Channels are valid (mono or stereo)
- [ ] File is decodable by soundfile

### 7. Optional transcription preprocessing (separate from stems)
When a stem will be used for AMT, optionally produce a preprocessed copy:
- Resample to 22050 Hz (Basic Pitch default)
- Convert to mono
- Store as `backend/data/<song_id>/stems_for_transcription/<stem_name>_preproc.wav`
- Preserve the original stem unchanged

### 8. Cache separation using composite key
Cache key: `sha256(source_audio) + engine + model + version + profile`  
If cached: skip separation, validate cached stems, update manifest.

### 9. Expose separation as a tracked job
- Status endpoint: `GET /api/songs/{song_id}/separation/status`
- Progress states: `queued → uploading → separating → validating → complete | failed`

### 10. Failure handling
- A missing or invalid stem must **never** silently masquerade as a successful one
- Manifest marks failed stems explicitly: `"guitar": { "status": "failed", "error": "..." }`
- Downstream transcription skips failed stems rather than crashing

### 11. Local vs Colab path
Both paths write identical on-disk structure and manifest schema.  
Colab path: user runs notebook, downloads zip, extracts to `backend/data/`  
Local path: `POST /api/import` runs separation in background thread (slow on CPU)

---

## Files to Create / Modify

```
backend/
  separation/
    __init__.py
    engine.py            # SeparationEngine Protocol + SeparationConfig
    engines/
      __init__.py
      demucs.py          # Demucs adapter (refactored from separation.py)
      spleeter.py        # Spleeter adapter (optional/CPU fallback)
      openunmix.py       # Open-Unmix adapter (optional)
    validation.py        # stem validation utilities
    preprocessing.py     # AMT preprocessing helpers
```

Modify:
- `backend/separation.py` → migrate logic into `backend/separation/engines/demucs.py`
- `backend/main.py` → update import path; add separation status endpoint
- `colab/mwtn_notebook.ipynb` → add profile selection cell; add validation cell

---

## Colab / Mobile Data Implications

| Action | Data Cost | Trigger |
|---|---|---|
| htdemucs_6s weights | ~80 MB | First Colab session (cached) |
| mdx_extra weights | ~83 MB | Only if vocal_focus profile selected |
| bag-of-models ensemble | ~400 MB | Only if max_quality selected — warn user |
| Spleeter install + weights | ~150 MB | Only if cpu_only profile |

> ⚠️ Warn users explicitly before activating `max_quality` profile — the ~400 MB checkpoint download is significant.

---

## Expected Results

- Every transcription run starts from validated, traceable stems
- Users can select a quality/performance profile appropriate to their use case
- Separation outputs are reusable across multiple analyses via caching
- MWTN can adopt better separation engines in the future with minimal changes
- Failed stems are clearly reported; the pipeline degrades gracefully

---

## Acceptance Criteria

- [ ] A source song produces validated standard stems via htdemucs_6s
- [ ] Stem generation is resumable from cache
- [ ] Manifest records exact separation model, version, and profile
- [ ] Missing / failed stems are clearly reported in the manifest
- [ ] Existing MWTN import workflow continues to work
- [ ] Preprocessed AMT copies are stored separately from original stems
- [ ] Separation profile is selectable via config or API parameter
