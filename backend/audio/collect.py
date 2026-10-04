"""
collect.py — Post-separation stem collection helpers.

Ported from StemDeck app/pipeline/collect.py (Apache-2.0).

After Demucs produces stems, this module:
  - Scans all stem WAVs for waveform peaks (peaks.json) and RMS
  - Computes stem presence percentages (0-100) for display
  - Builds 'original.wav' (complement of selected stems) for the studio
  - Handles TTL-based sweep of old song directories

These are called from main.py's import pipeline and from ingest.py.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("mwtn.collect")

_PEAK_POINTS = 3000  # matches StemDeck — enough for deepest zoom

STEM_NAMES = ("vocals", "drums", "bass", "guitar", "piano", "other")


def _run_ffmpeg(cmd: list[str]) -> bool:
    """Run an ffmpeg command. Returns True on success."""
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _, stderr = proc.communicate(timeout=300)
        if proc.returncode != 0:
            tail = (stderr or b"").decode(errors="replace").splitlines()[-3:]
            logger.warning("ffmpeg exit %s: %s", proc.returncode, " | ".join(tail))
            return False
        return True
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        logger.warning("ffmpeg timed out")
        return False


def compute_stem_peaks(stems_dir: Path, stem_names: list[str]) -> dict[str, float]:
    """
    Scan each stem WAV for [min,max] waveform peaks and RMS in a single pass.
    Writes peaks.json (for the waveform display) and returns per-stem RMS.

    Non-fatal: a failure here degrades to client-side decode; never breaks import.
    """
    from audio.waveform_scan import scan_stem

    peaks: dict[str, list[list[float]]] = {}
    rms_values: dict[str, float] = {}

    for name in stem_names:
        path = stems_dir / f"{name}.wav"
        if not path.is_file():
            continue
        try:
            result, rms = scan_stem(path, _PEAK_POINTS)
            if not result:
                continue
            peaks[name] = result
            rms_values[name] = rms
        except Exception:
            logger.warning("could not compute peaks for %s/%s", stems_dir.name, name, exc_info=True)

    if peaks:
        try:
            tmp = stems_dir / "peaks.json.tmp"
            tmp.write_text(json.dumps(peaks), encoding="utf-8")
            tmp.replace(stems_dir / "peaks.json")
        except Exception:
            logger.warning("could not write peaks.json for %s", stems_dir.name, exc_info=True)

    return rms_values


def merge_stem_peaks(stems_dir: Path, new_names: list[str]) -> dict[str, float]:
    """
    Add peaks/RMS for newly-produced stems into an existing peaks.json.
    Used when vocal lead/backing split adds new stems to a finished song.
    """
    from audio.waveform_scan import scan_stem

    peaks_path = stems_dir / "peaks.json"
    peaks: dict[str, list[list[float]]] = {}
    rms_values: dict[str, float] = {}

    if peaks_path.is_file():
        try:
            peaks = json.loads(peaks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("could not read existing peaks.json in %s", stems_dir, exc_info=True)

    for name in new_names:
        wav = stems_dir / f"{name}.wav"
        if not wav.is_file():
            continue
        try:
            result, rms = scan_stem(wav, _PEAK_POINTS)
            rms_values[name] = rms
            if result:
                peaks[name] = result
        except Exception:
            logger.warning("could not compute peaks for %s/%s", stems_dir.name, name, exc_info=True)

    try:
        tmp = stems_dir / "peaks.json.tmp"
        tmp.write_text(json.dumps(peaks), encoding="utf-8")
        tmp.replace(peaks_path)
    except Exception:
        logger.warning("could not write peaks.json for %s", stems_dir.name, exc_info=True)

    return rms_values


def compute_stem_presence(rms_values: dict[str, float]) -> dict[str, int]:
    """
    Convert per-stem RMS to 0-100 presence percentages.
    The loudest stem is 100%; all others are relative to it.
    """
    if not rms_values:
        return {}
    loudest = max(rms_values.values())
    if loudest < 1e-9:
        return {name: 0 for name in rms_values}
    return {
        name: max(0, min(100, round(rms / loudest * 100)))
        for name, rms in rms_values.items()
    }


def compute_stem_presence_from_wavs(song_dir: Path) -> dict[str, int]:
    """
    Compute stem presence percentages by streaming each WAV from disk.

    Uses soundfile.blocks() so the full audio is never loaded into RAM —
    safe for large 6-stem WAV sets on a 16 GB machine.

    Returns the cached result from stem_presence.json when available.
    Writes stem_presence.json on success (atomic replace).
    """
    cache_path = song_dir / "stem_presence.json"
    if cache_path.is_file():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    rms_values: dict[str, float] = {}

    try:
        import soundfile as sf
        import numpy as np

        for wav_path in sorted(song_dir.glob("*.wav")):
            name = wav_path.stem
            # Skip utility files
            if name in ("original", "click"):
                continue
            try:
                rms_accum = 0.0
                n_samples  = 0
                with sf.SoundFile(str(wav_path)) as f:
                    block_size = f.samplerate * 4  # 4-second blocks
                    for block in f.blocks(blocksize=block_size, dtype="float32"):
                        mono = block.mean(axis=1) if block.ndim > 1 else block
                        rms_accum += float(np.sum(mono ** 2))
                        n_samples  += len(mono)
                if n_samples > 0:
                    rms_values[name] = float(np.sqrt(rms_accum / n_samples))
            except Exception:
                logger.warning(
                    "compute_stem_presence_from_wavs: could not scan %s", wav_path.name,
                    exc_info=True
                )

    except ImportError:
        logger.warning(
            "compute_stem_presence_from_wavs: soundfile not available — returning empty"
        )
        return {}

    presence = compute_stem_presence(rms_values)

    if presence:
        try:
            tmp = cache_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(presence), encoding="utf-8")
            tmp.replace(cache_path)
        except Exception:
            logger.warning(
                "compute_stem_presence_from_wavs: could not write cache for %s",
                song_dir.name, exc_info=True
            )

    return presence


def presence_for_split(
    rms_values: dict[str, float],
    stem_presence: dict[str, int] | None,
    *,
    reference: str = "vocals",
) -> dict[str, int]:
    """
    Extend presence percentages to new stems (e.g. lead/backing vocal split)
    without re-decoding all existing stems. Recovers the loudest-stem baseline
    from one reference stem whose RMS and presence are both known.
    """
    reference_rms = rms_values.get(reference)
    reference_pct = (stem_presence or {}).get(reference)
    if not reference_rms or not reference_pct:
        return {}
    loudest = reference_rms / (reference_pct / 100)
    if loudest < 1e-9:
        return {}
    return {
        name: max(0, min(100, round(rms / loudest * 100)))
        for name, rms in rms_values.items()
        if name != reference
    }


def make_original_track(
    job_dir: Path,
    stems_dir: Path,
    selected_stems: list[str],
    ffmpeg_bin: str = "ffmpeg",
) -> Path | None:
    """
    Build stems/original.wav as the sum of stems the user did NOT select.
    This way the studio can play (original + each selected stem) and reconstruct
    the full song without doubling the selected stems.
    Skipped when all stems were selected (no complement to mix).
    """
    unselected = [s for s in STEM_NAMES if s not in selected_stems]
    inputs = [stems_dir / f"{name}.wav" for name in unselected]
    inputs = [p for p in inputs if p.exists()]
    if not inputs:
        return None

    out = stems_dir / "original.wav"
    cmd: list[str] = [ffmpeg_bin, "-y", "-nostdin", "-loglevel", "error"]
    for p in inputs:
        cmd += ["-i", str(p)]

    if len(inputs) == 1:
        cmd += ["-c:a", "pcm_s16le", str(out)]
    else:
        filter_inputs = "".join(f"[{i}:a]" for i in range(len(inputs)))
        cmd += [
            "-filter_complex",
            f"{filter_inputs}amix=inputs={len(inputs)}:normalize=0",
            "-c:a", "pcm_s16le",
            str(out),
        ]

    return out if _run_ffmpeg(cmd) else None
