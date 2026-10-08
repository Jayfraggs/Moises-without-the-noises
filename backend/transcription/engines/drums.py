from __future__ import annotations

from typing import Protocol, runtime_checkable

import librosa

from backend.schema.events import DrumHitEvent
from backend.transcription.config import TranscriptionConfig


@runtime_checkable
class AMTEngine(Protocol):
    def supports(self, stem_type: str, quality_profile: str) -> bool: ...
    def transcribe(self, audio_path: str, config: "TranscriptionConfig") -> list: ...
    def health_check(self) -> bool: ...
    def model_info(self) -> dict: ...


DRUM_LABEL_MAP = {
    "KD": "kick",
    "BD": "kick",
    "SD": "snare",
    "SN": "snare",
    "HH": "hihat_closed",
    "HHC": "hihat_closed",
    "HHO": "hihat_open",
    "TT": "tom_mid",
    "LT": "tom_low",
    "HT": "tom_high",
    "CY": "crash",
    "CR": "crash",
    "RD": "ride",
}


class ADTLibEngine:
    def supports(self, stem_type: str, quality_profile: str) -> bool:
        return stem_type == "drums"

    def health_check(self) -> bool:
        try:
            import adtlib  # noqa: F401
            return True
        except ImportError:
            return False

    def model_info(self) -> dict:
        return {
            "engine": "adtlib",
            "license": "MIT",
            "polyphonic": False,
            "stems": ["drums"],
            "data_cost_mb": 30,
        }

    def transcribe(self, audio_path: str, config: TranscriptionConfig) -> list[DrumHitEvent]:
        if not self.health_check():
            raise RuntimeError("adtlib is not installed or unavailable")

        try:
            import adtlib
        except ImportError as exc:  # pragma: no cover - health_check guards this path
            raise RuntimeError(f"adtlib failed to import: {exc}") from exc

        try:
            result = adtlib.transcribe(str(audio_path))
        except Exception as exc:
            raise RuntimeError(f"ADTLib inference failed: {exc}") from exc

        hits: list[DrumHitEvent] = []
        for entry in result or []:
            try:
                time_s, label, velocity = entry
            except (TypeError, ValueError):
                continue

            time_float = float(time_s)
            normalized_label = str(label).upper()
            mapped = DRUM_LABEL_MAP.get(normalized_label, "unknown")
            vel = int(velocity) if velocity is not None else None

            hits.append(
                DrumHitEvent(
                    start_time=time_float,
                    end_time=None,
                    drum_type=mapped,
                    velocity=vel,
                    confidence=1.0,
                    source_model="adtlib",
                    track_id="drums",
                )
            )

        return sorted(hits, key=lambda item: item.start_time)
