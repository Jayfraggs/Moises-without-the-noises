"""Pure movable-do solfège resolution for canonical musical events."""

from __future__ import annotations

from dataclasses import dataclass

from backend.schema.events import MusicalEventBase

MAJOR_SOLFA: tuple[str, ...] = (
    "Do", "Ra", "Re", "Me", "Mi", "Fa", "Se", "Sol", "Le", "La", "Te", "Ti",
)
PITCH_CLASS_NAMES: tuple[str, ...] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
)


@dataclass(frozen=True)
class SolfaResult:
    """Resolved solfège events and the key context used to derive them."""

    events: list[MusicalEventBase]
    tonic_midi: int
    tonic_name: str
    mode: str


def _normalize_mode(mode: str) -> str:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"major", "minor"}:
        raise ValueError("mode must be either 'major' or 'minor'")
    return normalized_mode


def _solfa_for_pitch(pitch_midi: int | None, tonic_midi: int, mode: str, minor_as_la: bool) -> str | None:
    """Resolve a MIDI pitch to its movable-do syllable, preserving rests."""
    if pitch_midi is None or pitch_midi == 0:
        return None

    relative_pitch = (pitch_midi - tonic_midi) % 12
    if mode == "minor" and minor_as_la:
        return MAJOR_SOLFA[(relative_pitch + 9) % 12]
    return MAJOR_SOLFA[relative_pitch]


def resolve_solfa(
    events: list[MusicalEventBase],
    tonic_midi: int,
    mode: str,
    minor_as_la: bool = True,
) -> SolfaResult:
    """Return copied events with tonic-relative movable-do solfège attached.

    The resolver has no audio dependencies and never mutates the supplied event
    objects. Events without a ``midi_pitch`` attribute, and MIDI pitch ``0``,
    are treated as rests.
    """
    normalized_mode = _normalize_mode(mode)
    if not isinstance(tonic_midi, int):
        raise TypeError("tonic_midi must be an integer MIDI note")

    resolved_events: list[MusicalEventBase] = []
    for event in events:
        pitch_midi = getattr(event, "midi_pitch", None)
        solfa = _solfa_for_pitch(pitch_midi, tonic_midi, normalized_mode, minor_as_la)
        resolved_events.append(event.model_copy(update={"solfa": solfa}))

    return SolfaResult(
        events=resolved_events,
        tonic_midi=tonic_midi,
        tonic_name=PITCH_CLASS_NAMES[tonic_midi % 12],
        mode=normalized_mode,
    )


__all__ = ["MAJOR_SOLFA", "SolfaResult", "resolve_solfa"]
