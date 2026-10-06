from __future__ import annotations

import os
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from backend.transcription.config import TranscriptionConfig


def _ensure_temp_path(prefix: str = "mwtn_preproc_") -> Path:
    fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=".wav")
    os.close(fd)
    return Path(temp_path)


def preprocess_for_transcription(audio_path: str | Path, config: TranscriptionConfig) -> Path:
    """Load, normalize, and resample audio to a temp WAV file for transcription."""
    source_path = Path(audio_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    audio, source_sr = sf.read(str(source_path), always_2d=False, dtype="float32")

    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    audio = np.asarray(audio, dtype=np.float32)

    if source_sr != config.sample_rate:
        audio = librosa.resample(audio, orig_sr=source_sr, target_sr=config.sample_rate)

    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 0:
        audio = audio / (peak + 1e-8)

    out_path = _ensure_temp_path()
    sf.write(str(out_path), audio.astype(np.float32), config.sample_rate)
    return out_path


def chunk_audio(audio_path: str | Path, chunk_s: float, overlap_s: float, sr: int) -> list[tuple[Path, float]]:
    """Split audio into overlapping chunks for long transcription runs."""
    source_path = Path(audio_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    audio, _ = sf.read(str(source_path), always_2d=False, dtype="float32")
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    audio = np.asarray(audio, dtype=np.float32)

    duration = float(len(audio)) / float(sr)
    if duration <= (chunk_s + overlap_s):
        return [(source_path, 0.0)]

    chunk_samples = int(max(1, chunk_s * sr))
    overlap_samples = int(max(0, overlap_s * sr))
    step = chunk_samples - overlap_samples

    results: list[tuple[Path, float]] = []
    for start_idx in range(0, len(audio), step):
        end_idx = min(start_idx + chunk_samples, len(audio))
        chunk = audio[start_idx:end_idx]
        if len(chunk) == 0:
            continue

        chunk_path = _ensure_temp_path()
        sf.write(str(chunk_path), chunk.astype(np.float32), sr)
        results.append((chunk_path, float(start_idx / sr)))

    if not results:
        chunk_path = _ensure_temp_path()
        sf.write(str(chunk_path), audio.astype(np.float32), sr)
        return [(chunk_path, 0.0)]

    return results


def merge_chunked_events(chunk_results: list[tuple[list, float]], onset_tolerance_s: float = 0.02) -> list:
    """Merge events from overlapping chunks and remove duplicates by onset + pitch."""

    def normalize_event(event):
        if hasattr(event, "model_dump"):
            return event.model_dump(mode="json")
        if isinstance(event, dict):
            return event.copy()
        return dict(event)

    remapped: list = []
    for events, offset in chunk_results:
        if not events:
            continue
        for event in events:
            remapped_event = normalize_event(event)
            if "start_time" in remapped_event:
                remapped_event["start_time"] = float(remapped_event["start_time"]) + float(offset)
            if "end_time" in remapped_event and remapped_event["end_time"] is not None:
                remapped_event["end_time"] = float(remapped_event["end_time"]) + float(offset)
            remapped.append(remapped_event)

    if not remapped:
        return []

    deduped: list = []
    for event in sorted(remapped, key=lambda item: float(item.get("start_time", 0.0))):
        keep = True
        for index, existing in enumerate(deduped):
            start_delta = abs(float(event.get("start_time", 0.0)) - float(existing.get("start_time", 0.0)))
            same_pitch = event.get("midi_pitch") == existing.get("midi_pitch")
            if start_delta < onset_tolerance_s and same_pitch:
                if float(event.get("confidence", 0.0)) > float(existing.get("confidence", 0.0)):
                    deduped[index] = event
                keep = False
                break
        if keep:
            deduped.append(event)

    return sorted(deduped, key=lambda item: float(item.get("start_time", 0.0)))


def cleanup_temp_files(paths: list[Path]) -> None:
    """Delete temp files if they still exist."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
