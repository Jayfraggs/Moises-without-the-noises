"""
section_detection.py — Automatic song-structure section detection.

Uses the `allin1` library (Taejun Kim et al., ISMIR 2023, MIT licence)
which wraps the Harmonix-trained model that simultaneously detects:
  - Beat and downbeat positions
  - Functional segment boundaries (intro, verse, chorus, bridge, outro…)
  - The segment label for each boundary

pip install allin1
  → downloads ~120 MB model checkpoint on first use (cached in
    ~/.cache/allin1/ so subsequent runs are instant).

Data cost note: ~120 MB on first Colab session.  The model is cached in
/root/.cache/allin1/ on Colab — it is NOT saved to Drive by default and
will re-download each new Colab session unless you point HF_HOME to Drive.

Fallback: if allin1 is unavailable we attempt a lightweight heuristic
using librosa's novelty-based segmentation (no extra install required).
The heuristic labels all segments as "part" with no semantic labels.

Output is normalised through audio/sections.py so the schema is
identical regardless of which path was taken.
"""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

logger = logging.getLogger("mwtn.section_detection")

# allin1 label → mwtn section kind mapping
_LABEL_MAP: dict[str, str] = {
    "intro":        "intro",
    "outro":        "outro",
    "verse":        "verse",
    "chorus":       "chorus",
    "bridge":       "bridge",
    "break":        "break",
    "instrumental": "inst",
    "inst":         "inst",
    "solo":         "solo",
    "pre-chorus":   "verse",   # closest available kind
    "pre_chorus":   "verse",
    "post-chorus":  "verse",
    "post_chorus":  "verse",
    "interlude":    "bridge",
    "transition":   "break",
    "silence":      "break",
}
_DEFAULT_KIND = "part"
ALLIN1_TIMEOUT_SECONDS = 12.0


def _map_label(label: str) -> str:
    return _LABEL_MAP.get(label.lower().strip(), _DEFAULT_KIND)


# ── allin1 path ───────────────────────────────────────────────────────────────

def _detect_with_allin1(audio_path: Path, duration: float) -> list[dict] | None:
    """
    Run allin1.analyze() and convert its segment output to raw segment dicts
    suitable for normalize_sections().  Returns None on any import or runtime
    error so the caller can fall through to the heuristic.
    """
    try:
        import allin1
    except ImportError:
        return None

    try:
        logger.info("section_detection: running allin1 on %s", audio_path.name)

        result_holder: dict[str, object] = {}
        exc_holder: dict[str, Exception] = {}

        def _analyze() -> None:
            try:
                result_holder["result"] = allin1.analyze(str(audio_path))
            except Exception as exc:  # pragma: no cover - exercised via timeout regression
                exc_holder["exc"] = exc

        worker = threading.Thread(target=_analyze, daemon=True)
        worker.start()
        worker.join(ALLIN1_TIMEOUT_SECONDS)

        if worker.is_alive():
            logger.warning(
                "section_detection: allin1 timed out after %.1f seconds on %s",
                ALLIN1_TIMEOUT_SECONDS,
                audio_path.name,
            )
            return None

        if "exc" in exc_holder:
            raise exc_holder["exc"]

        result = result_holder.get("result")
        # result.segments: list of SegmentObject with .start, .end, .label
        segments = getattr(result, "segments", None)
        if not segments:
            return None

        raw: list[dict] = []
        for seg in segments:
            start = float(getattr(seg, "start", 0))
            end   = float(getattr(seg, "end", duration))
            label = str(getattr(seg, "label", "part"))
            raw.append({"start": start, "end": end, "label": _map_label(label)})

        return raw if len(raw) >= 2 else None

    except Exception as exc:
        logger.warning("section_detection: allin1 failed: %s", exc)
        return None


# ── librosa heuristic fallback ────────────────────────────────────────────────

def _detect_with_librosa(audio_path: Path, duration: float) -> list[dict] | None:
    """
    Lightweight novelty-based segmentation via librosa.
    Labels all segments as 'part' (no semantic labels).
    Returns None only if librosa is unavailable or the track is too short.
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        return None

    try:
        logger.info("section_detection: running librosa heuristic on %s", audio_path.name)
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True, duration=min(duration, 600))

        # Onset novelty is the simplest stable fallback across librosa versions.
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
        novelty = librosa.util.normalize(onset)

        boundary_frames = librosa.util.peak_pick(
            novelty,
            pre_max=1,
            post_max=1,
            pre_avg=3,
            post_avg=3,
            delta=0.15,
            wait=max(2, int(sr * 6 / 512)),
        )
        boundary_times = librosa.frames_to_time(boundary_frames, sr=sr, hop_length=512).tolist()

        if not boundary_times:
            # Fallback for very quiet/boring material: split into a few equal sections.
            step = duration / 4.0
            edges = [0.0, step, step * 2, step * 3, duration]
        else:
            edges = [0.0] + [round(float(t), 3) for t in boundary_times if 0.0 < float(t) < duration] + [round(float(duration), 3)]
            edges = sorted(set(round(float(v), 3) for v in edges))

        raw: list[dict] = []
        for i in range(len(edges) - 1):
            s, e = edges[i], edges[i + 1]
            if e - s >= 1.0:
                raw.append({"start": float(s), "end": float(e), "label": "part"})

        return raw if len(raw) >= 2 else None

    except Exception as exc:
        logger.warning("section_detection: librosa heuristic failed: %s", exc)
        return None


# ── Public entry point ────────────────────────────────────────────────────────

def detect_sections(song_dir: Path, report=None) -> list[dict]:
    """
    Detect song sections for the given song directory.

    Tries allin1 first, falls back to librosa heuristic.
    Normalises output through audio.sections.normalize_sections().
    Writes sections.json and returns the normalised list.

    Parameters
    ----------
    song_dir : Path
        Must contain at least one stem WAV and a manifest.json.
    report : callable(str) | None
        Progress callback.

    Returns
    -------
    list[dict]
        Normalised section records (same schema as PATCH /sections).
        Empty list on failure.
    """
    from audio.sections import normalize_sections

    def _report(msg: str) -> None:
        if report:
            report(msg)
        logger.info(msg)

    # ── Pick audio source ─────────────────────────────────────────────────────
    # Prefer a mix/full-mix stem; fall back to the first available stem.
    _SOURCE_PREF = ("other", "vocals", "bass", "drums", "guitar", "piano")
    source: Path | None = None
    for name in _SOURCE_PREF:
        candidate = song_dir / f"{name}.wav"
        if candidate.is_file():
            source = candidate
            break
    if source is None:
        for wav in song_dir.glob("*.wav"):
            source = wav
            break
    if source is None:
        _report("section_detection: no WAV stems found")
        return []

    # ── Get duration ──────────────────────────────────────────────────────────
    try:
        import soundfile as sf
        info = sf.info(str(source))
        duration = float(info.frames) / info.samplerate
    except Exception as exc:
        _report(f"section_detection: could not read duration: {exc}")
        return []

    if duration < 10.0:
        _report("section_detection: track too short (<10 s)")
        return []

    # ── Detection ─────────────────────────────────────────────────────────────
    _report("Detecting song sections with allin1…")
    raw = _detect_with_allin1(source, duration)

    if raw is None:
        _report("allin1 unavailable or failed — using librosa heuristic…")
        raw = _detect_with_librosa(source, duration)

    if not raw:
        _report("section_detection: no segments produced")
        return []

    # ── Normalise ─────────────────────────────────────────────────────────────
    sections = normalize_sections(raw, duration)
    if not sections:
        _report("section_detection: normalization produced empty result")
        return []

    # ── Persist ───────────────────────────────────────────────────────────────
    import json
    sections_path = song_dir / "sections.json"
    tmp = sections_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")
    tmp.replace(sections_path)

    _report(f"section_detection: {len(sections)} sections detected and saved")
    return sections
