# Plan 13 — Artifact Caching, Performance and Storage Management

## Motive

Separation and transcription are the most expensive operations in the pipeline — separation takes 2–5 minutes per song on Colab GPU, and AMT transcription adds several more minutes per stem. Recomputing these every time the user changes a display option, adjusts the key, or exports a different format would make MWTN frustrating and wasteful of Colab GPU quota.

The caching layer ensures that only the operations that actually need to re-run do so.

---

## Caching Architecture

### Two-tier cache

**Tier 1 — Source-level immutable cache**
Expensive, hardware-dependent operations. Valid as long as the source audio and model/config are unchanged.

| Operation | Cache key | Cache location |
|---|---|---|
| Source separation | `sha256(source_audio) + engine + model + version + profile` | `backend/data/<song_id>/stems/` |
| AMT transcription | `sha256(stem_audio) + engine + model + version + config_hash` | `backend/data/<song_id>/transcription_cache/` |
| Beat tracking | `sha256(source_audio) + tracker + version + config_hash` | `backend/data/<song_id>/beats.json` |
| Harmonic analysis | `sha256(source_audio) + chord_engine + version` | `backend/data/<song_id>/chords.json` |
| Lyric transcription | `sha256(vocals_stem) + whisper_model + language` | `backend/data/<song_id>/lyrics.json` |

**Tier 2 — Derived artifact cache**
Fast, CPU-only operations. Valid as long as their Tier 1 inputs and user corrections are unchanged.

| Operation | Depends on | Cache location |
|---|---|---|
| Quantization | transcription + beat grid | embedded in event JSON |
| Solfa events | transcription + key map + corrections | `backend/data/<song_id>/solfa.json` |
| MusicXML | transcription + beats + key + chords + lyrics + corrections | `backend/data/<song_id>/scores/` |
| MIDI | transcription + beats + corrections | `backend/data/<song_id>/scores/` |
| Lyric alignment | lyrics + transcription | `backend/data/<song_id>/lyrics_alignment.json` |

---

## Cache Key Computation

```python
import hashlib, json

def compute_cache_key(*components) -> str:
    combined = json.dumps(components, sort_keys=True, default=str)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]

# Example for transcription:
cache_key = compute_cache_key(
    stem_audio_sha256,
    "basic_pitch",
    "0.3.1",
    {"onset_threshold": 0.5, "frame_threshold": 0.3}
)
```

Cache keys are stored in the artifact registry (Plan 01).

---

## Cache Invalidation

### When to invalidate Tier 1 (separation, transcription)
- Source audio file changes (hash changes)
- Separation model or version changes
- Transcription model or version changes
- Transcription config changes

### When to invalidate Tier 2 (solfa, MusicXML, MIDI)
- Any Tier 1 result it depends on is invalidated
- User corrections are applied (but corrections themselves don't invalidate; they are applied on top)
- Key map changes → invalidate solfa, MusicXML key signature
- Chord events change → invalidate MusicXML chord symbols
- Lyric alignment changes → invalidate MusicXML lyrics

**Critical rule:** Cache invalidation must never delete source audio or user corrections.

### Staleness tracking
Each artifact in the registry has an `is_stale: bool` field. The system sets `is_stale = true` when any dependency changes, rather than immediately deleting the artifact. This allows the user to see the stale state in the UI (Plan 11) before deciding to regenerate.

---

## Avoiding Redundant Recomputation

| User action | What reruns | What does NOT rerun |
|---|---|---|
| Change solfa display key | Solfa events only | Separation, transcription, beats, chords |
| Export MIDI (if MusicXML already generated) | Nothing (reuse score model) | Everything |
| Correct a single note pitch | Solfa, MusicXML, MIDI | Separation, transcription, beats, chords |
| Change quantization strength | Quantization, MusicXML, MIDI, Solfa | Separation, transcription |
| Re-run chord detection | Chords, MusicXML chord symbols | Separation, transcription, solfa |

---

## Storage Layout

```
backend/data/<song_id>/
  source/
    original.mp3           # source audio — never deleted by cache logic
  stems/
    vocals.wav             # Tier 1 — cached per source hash + model
    bass.wav
    ...
  stems_for_transcription/
    vocals_preproc.wav     # preprocessed for AMT — rederivable from stems
  transcription_cache/
    vocals_<cache_key>.json
    piano_<cache_key>.json
  analysis/
    beats.json             # cached beat grid
    key.json               # cached key map
    chords.json            # cached chord events
  lyrics/
    lyrics.json            # Whisper output — cached
    lyrics_alignment.json  # derived — rederivable
  scores/
    melody_v1.xml
    full_score_v1.xml
    melody_v1.mid
  solfa.json               # derived — rederivable
  corrections.json         # user corrections — NEVER deleted automatically
  manifest.json            # project manifest
```

---

## Disk Space Reporting

```
GET /api/songs/{song_id}/storage
returns:
{
  "total_bytes": 245000000,
  "source_bytes": 8000000,
  "stems_bytes": 180000000,
  "transcription_cache_bytes": 12000000,
  "scores_bytes": 1500000,
  "can_free_bytes": 195000000,   // stems + cache (rederivable from Colab)
  "permanent_bytes": 8000000     // source + corrections + manifest
}
```

---

## Deletion Rules

| Category | Safe to delete | Notes |
|---|---|---|
| Source audio | ❌ Never auto-delete | User-owned; not rederivable from Colab without re-upload |
| User corrections | ❌ Never auto-delete | User work product |
| Stems | ✅ | Rederivable via Colab |
| Transcription cache | ✅ | Rederivable via Colab |
| Analysis files | ✅ | Fast to recompute |
| Scores | ✅ if not user-edited | MusicXML/MIDI marked `user_edited` are protected |
| Solfa/alignment | ✅ | Pure derived; recomputes in seconds |

API for deletion:
```
DELETE /api/songs/{song_id}/cache?tier=derived
DELETE /api/songs/{song_id}/cache?tier=all
DELETE /api/songs/{song_id}                    # full project delete (requires confirmation)
```

---

## Concurrency Protection

When a job is running on a song, derived artifacts for that song are locked (read-only) until the job completes. This prevents a UI-triggered regeneration from writing to a file that the background job is also writing.

Simple file-based lock:
```
backend/data/<song_id>/.lock
```
Presence of `.lock` → song is being processed. The API returns `HTTP 409 Conflict` for write operations while locked.

---

## Files to Create

```
backend/
  cache/
    __init__.py
    keys.py           # cache key computation
    registry.py       # artifact registry read/write
    invalidation.py   # staleness detection + cascade
    storage.py        # disk usage reporting + safe deletion
    locks.py          # job concurrency locks
```

---

## Colab / Mobile Data Implications

The caching system has no additional data cost. It reduces data cost over time by avoiding unnecessary re-runs of Colab jobs for unchanged audio.

---

## Expected Results

- Repeated identical operations return cached results instantly
- Changing the key for solfa does not re-run separation or transcription
- Generating MIDI after MusicXML is already generated is nearly instantaneous
- Users understand what storage they're using and can safely reclaim space
- Concurrent jobs never corrupt each other's artifacts

---

## Acceptance Criteria

- [ ] Identical transcription jobs return cached results without re-running the model
- [ ] Changing the AMT model version produces a new artifact, not a cache hit
- [ ] Cache invalidation never deletes source audio or user corrections
- [ ] Concurrent job protection prevents mid-write reads of partial data
- [ ] Storage report endpoint returns accurate byte counts by category
- [ ] `DELETE /api/songs/{song_id}/cache?tier=derived` safely removes only derived files
