from __future__ import annotations

import os
import tempfile
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


class PianoKongEngine:
    def supports(self, stem_type: str, quality_profile: str) -> bool:
        return stem_type == "piano" and quality_profile == "high_quality"

    def health_check(self) -> bool:
        try:
            import piano_transcription_inference  # noqa: F401
            return True
        except ImportError:
            return False

    def model_info(self) -> dict:
        return {
            "engine": "piano_kong",
            "license": "MIT",
            "polyphonic": True,
            "stems": ["piano"],
            "profiles": ["high_quality"],
            "data_cost_mb": 350,
            "caveat": "Piano stems only. ~350 MB first-run download on Colab.",
        }

    def transcribe(self, audio_path: str, config: TranscriptionConfig) -> list[NoteEvent]:
        if not self.health_check():
            raise RuntimeError("piano_kong is not installed or unavailable")

        try:
            from piano_transcription_inference import PianoTranscription, load_audio, sample_rate as pt_sr
        except ImportError as exc:  # pragma: no cover - health_check guards this path
            raise RuntimeError(f"piano_kong failed to import: {exc}") from exc

        try:
            audio, _ = load_audio(str(audio_path), sr=pt_sr, mono=True)
            with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
                tmp_midi_path = tmp.name

            transcriptor = PianoTranscription(device=config.device, checkpoint_path=None)
            try:
                result = transcriptor.transcribe(audio, tmp_midi_path)
            finally:
                if os.path.exists(tmp_midi_path):
                    try:
                        os.unlink(tmp_midi_path)
                    except OSError:
                        pass

            est_events = result.get("est_note_events", []) if isinstance(result, dict) else []
            if not est_events:
                return []

            notes: list[NoteEvent] = []
            for event in est_events:
                try:
                    onset = float(event["onset_time"])
                    offset = float(event["offset_time"])
                    midi_note = int(event["midi_note"])
                    velocity = int(event["velocity"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError(f"piano_kong event payload was malformed: {event!r}") from exc

                duration = offset - onset
                if duration < (config.minimum_note_length_ms / 1000.0):
                    continue

                notes.append(
                    NoteEvent(
                        start_time=onset,
                        end_time=offset,
                        midi_pitch=midi_note,
                        frequency_hz=float(librosa.midi_to_hz(midi_note)),
                        velocity=velocity,
                        confidence=1.0,
                        source_model="piano_kong_1.0",
                        track_id=config.stem_type,
                    )
                )

            return sorted(notes, key=lambda item: item.start_time)
        except Exception as exc:
            raise RuntimeError(f"Piano Kong inference failed: {exc}") from exc
