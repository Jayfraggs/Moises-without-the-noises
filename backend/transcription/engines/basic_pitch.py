from __future__ import annotations

from typing import Protocol, runtime_checkable

import librosa

from backend.schema.events import NoteEvent
from backend.transcription.config import TranscriptionConfig


@runtime_checkable
class AMTEngine(Protocol):
    def supports(self, stem_type: str, quality_profile: str) -> bool: ...
    def transcribe(self, audio_path: str, config: "TranscriptionConfig") -> list: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...


class BasicPitchEngine:
    """NOTE: Guitar AMT quality via Basic Pitch is lower than piano or vocal transcription.
    Guitar stem outputs will typically require human review (Plan 10). This is a known
    limitation of all current open-source guitar AMT models, not a Basic Pitch-specific bug.
    """

    def supports(self, stem_type: str, quality_profile: str) -> bool:
        return stem_type in ("vocals", "bass", "guitar", "piano", "other") and quality_profile in (
            "standard",
            "high_quality",
        )

    def health_check(self) -> bool:
        try:
            from basic_pitch.inference import predict  # noqa: F401
            from basic_pitch import ICASSP_2022_MODEL_PATH  # noqa: F401
            return True
        except ImportError:
            return False

    def model_info(self) -> dict:
        try:
            import basic_pitch

            return {
                "engine": "basic_pitch",
                "version": basic_pitch.__version__,
                "license": "MIT",
                "polyphonic": True,
                "model": "ICASSP_2022",
                "data_cost_mb": 67,
            }
        except ImportError:
            return {"engine": "basic_pitch", "available": False}

    def transcribe(self, audio_path: str, config: TranscriptionConfig) -> list[NoteEvent]:
        if not self.health_check():
            raise ImportError("basic-pitch is not installed. Run: pip install basic-pitch")

        try:
            import basic_pitch
            from basic_pitch import ICASSP_2022_MODEL_PATH
            from basic_pitch.inference import predict
        except ImportError:  # pragma: no cover - guarded above, but keeps fallback safe.
            raise ImportError("basic-pitch is not installed. Run: pip install basic-pitch")

        model_output, midi_data, note_events = predict(
            audio_path,
            ICASSP_2022_MODEL_PATH,
            onset_threshold=config.onset_threshold,
            frame_threshold=config.frame_threshold,
            minimum_note_length=config.minimum_note_length_ms,
            minimum_frequency=config.minimum_frequency_hz,
            maximum_frequency=config.maximum_frequency_hz,
            melodia_trick=True,
        )

        if not note_events:
            return []

        events: list[NoteEvent] = []
        for start_s, end_s, pitch_midi, confidence, _pitch_bend in note_events:
            confidence_value = float(confidence)
            duration = float(end_s) - float(start_s)
            if confidence_value < config.minimum_confidence:
                continue
            if duration < (config.minimum_note_length_ms / 1000.0):
                continue

            events.append(
                NoteEvent(
                    start_time=float(start_s),
                    end_time=float(end_s),
                    midi_pitch=int(pitch_midi),
                    frequency_hz=float(librosa.midi_to_hz(pitch_midi)),
                    confidence=confidence_value,
                    velocity=None,
                    source_model=f"basic_pitch_{basic_pitch.__version__}",
                    track_id=config.stem_type,
                )
            )

        return sorted(events, key=lambda event: event.start_time)
