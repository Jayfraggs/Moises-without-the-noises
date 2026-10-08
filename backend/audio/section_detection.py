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
    Lightweight, version-tolerant fallback segmentation via librosa.

    This intentionally avoids the brittle onset/peak_pick chain that can fail on
    certain librosa versions or when the waveform is very quiet/monotone. Instead,
    it computes a simple energy envelope and produces stable boundaries by slicing
    the track into a handful of equal-length sections, which still yields valid
    section records for the app even when the model fails.
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        return None

    try:
        logger.info("section_detection: running librosa heuristic on %s", audio_path.name)
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True, duration=min(duration, 600))
        if y.size == 0:
            return None

        # Energy envelope is more stable than peak-picking onset novelty across
        # librosa versions and on quiet or repetitive tracks.
        frame_length = max(1024, int(sr * 0.5))
        hop_length = frame_length // 4
        energy = np.abs(librosa.stft(y, n_fft=frame_length, hop_length=hop_length))
        power = np.mean(np.square(energy), axis=0)
        if power.size == 0:
            return None

        # Smooth and convert to a small set of robust boundaries.
        smooth = np.convolve(power, np.ones(min(9, power.size)) / min(9, power.size), mode="same")
        baseline = float(np.median(smooth)) if smooth.size else 0.0
        threshold = max(float(np.max(smooth) * 0.35), baseline + 1e-9)

        # Use dynamic detection if the energy profile contains meaningful changes;
        # otherwise fall back to a uniform split to keep the detector usable.
        if np.any(smooth > threshold):
            change = np.diff(smooth)
            if change.size > 0:
                candidates = np.where(change > max(np.std(change) * 0.5, 1e-6))[0]
                if candidates.size > 0:
                    boundary_frames = np.unique(np.clip(candidates + 1, 0, smooth.size - 1))
                    boundary_times = librosa.frames_to_time(boundary_frames, sr=sr, hop_length=hop_length)
                    edges = [0.0] + [float(t) for t in boundary_times if 0.0 < float(t) < duration] + [float(duration)]
                    edges = sorted(set(round(float(v), 3) for v in edges))
                else:
                    edges = [0.0, duration]
            else:
                edges = [0.0, duration]
        else:
            edges = [0.0, duration]

        if len(edges) < 2:
            edges = [0.0, duration]

        # Ensure at least 2 sections, even on monotone material.
        if len(edges) == 2:
            sections_count = max(2, min(6, int(duration / 20.0)))
            step = duration / float(sections_count)
            edges = [0.0] + [round(float(i * step), 3) for i in range(1, sections_count)] + [round(float(duration), 3)]

        raw: list[dict] = []
        for i in range(len(edges) - 1):
            s, e = edges[i], edges[i + 1]
            if e - s >= 1.0:
                raw.append({"start": float(s), "end": float(e), "label": "part"})

        if len(raw) < 2:
            sections_count = max(2, min(6, int(duration / 15.0)))
            step = duration / float(sections_count)
            raw = [
                {"start": float(i * step), "end": float((i + 1) * step), "label": "part"}
                for i in range(sections_count)
            ]
            raw[0]["start"] = 0.0
            raw[-1]["end"] = float(duration)

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
    # Prefer the longest, most informative stem instead of blindly taking the
    # first available file in a fixed preference order. This avoids choosing a
    # short vocal or percussion stem when a full-length bass or mix stem is
    # present for section detection.
    candidates: list[tuple[float, Path]] = []
    for name in ("other", "vocals", "bass", "drums", "guitar", "piano"):
        candidate = song_dir / f"{name}.wav"
        if candidate.is_file():
            candidates.append((candidate.stat().st_size, candidate))
    if not candidates:
        for wav in song_dir.glob("*.wav"):
            candidates.append((wav.stat().st_size, wav))

    if not candidates:
        _report("section_detection: no WAV stems found")
        return []

    source = max(candidates, key=lambda item: item[0])[1]

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
