from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import librosa
import numpy as np

from backend.schema.events import NoteEvent
from backend.transcription.config import TranscriptionConfig


@runtime_checkable
class AMTEngine(Protocol):
    def supports(self, stem_type: str, quality_profile: str) -> bool: ...
    def transcribe(self, audio_path: str, config: "TranscriptionConfig") -> list: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...


class PYINEngine:
    def supports(self, stem_type: str, quality_profile: str) -> bool:
        return stem_type in ("vocals", "bass") and quality_profile == "fast"

    def health_check(self) -> bool:
        try:
            import librosa as _librosa  # noqa: F401
            return True
        except ImportError:
            return False

    def model_info(self) -> dict:
        return {
            "engine": "pyin",
            "library": "librosa",
            "version": librosa.__version__,
            "polyphonic": False,
        }

    def transcribe(self, audio_path: str, config: TranscriptionConfig) -> list[NoteEvent]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(audio_path)

        y, sr = librosa.load(audio_path, sr=config.sample_rate, mono=True)
        hop_length = 512
        f0, voiced_flag, voiced_prob = librosa.pyin(
            y,
            fmin=config.minimum_frequency_hz,
            fmax=config.maximum_frequency_hz,
            sr=sr,
            frame_length=2048,
            hop_length=hop_length,
        )

        voiced_flag = np.asarray(voiced_flag, dtype=bool)
        f0_values = np.asarray(f0, dtype=float)
        prob_values = np.asarray(voiced_prob, dtype=float)

        events: list[NoteEvent] = []
        run_start: int | None = None
        run_end: int | None = None

        def flush_run(start_idx: int, end_idx: int) -> None:
            nonlocal run_start, run_end
            if start_idx is None or end_idx is None:
                return

            valid_freqs = [
                float(freq)
                for freq in f0_values[start_idx : end_idx + 1]
                if np.isfinite(freq)
            ]
            if not valid_freqs:
                run_start = None
                run_end = None
                return

            frequency_hz = float(np.median(valid_freqs))
            midi_pitch = int(round(librosa.hz_to_midi(frequency_hz)))
            midi_pitch = max(0, min(127, midi_pitch))

            valid_probs = [
                float(prob)
                for prob in prob_values[start_idx : end_idx + 1]
                if np.isfinite(prob)
            ]
            confidence = float(np.mean(valid_probs)) if valid_probs else 0.0
            confidence = max(0.0, min(1.0, confidence))

            start_time = float(start_idx * hop_length / sr)
            end_time = float((end_idx + 1) * hop_length / sr)
            duration = end_time - start_time

            if duration < (config.minimum_note_length_ms / 1000.0):
                run_start = None
                run_end = None
                return
            if confidence < config.minimum_confidence:
                run_start = None
                run_end = None
                return

            note = NoteEvent(
                track_id=config.stem_type,
                start_time=start_time,
                end_time=end_time,
                confidence=confidence,
                source_model=f"pyin_librosa_{librosa.__version__}",
                midi_pitch=midi_pitch,
                frequency_hz=frequency_hz,
                velocity=None,
            )
            events.append(note)
            run_start = None
            run_end = None

        for idx in range(len(voiced_flag)):
            is_voiced = bool(voiced_flag[idx])
            if is_voiced:
                if run_start is None:
                    run_start = idx
                run_end = idx
                continue

            if run_start is not None and run_end is not None:
                flush_run(run_start, run_end)

        if run_start is not None and run_end is not None:
            flush_run(run_start, run_end)

        return sorted(events, key=lambda event: event.start_time)
