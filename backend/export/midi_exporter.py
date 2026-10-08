"""Multi-track MIDI export from canonical musical events."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import mido


class MusicalEvent(Protocol):
    """Minimum event attributes consumed by the MIDI exporter."""

    onset_s: float
    duration_s: float
    pitch_midi: int | None
    velocity: int | None


STEM_CHANNELS: dict[str, int] = {
    "vocals": 0,
    "bass": 1,
    "guitar": 2,
    "piano": 3,
    "other": 4,
    "drums": 9,
}
TICKS_PER_BEAT = 480
DEFAULT_VELOCITY = 80


def _value(event: Any, name: str, legacy_name: str | None = None) -> Any:
    value = getattr(event, name, None)
    if value is None and legacy_name is not None:
        value = getattr(event, legacy_name, None)
    return value


def _ticks(seconds: float, tempo_bpm: float) -> int:
    return max(0, round(seconds * (TICKS_PER_BEAT * tempo_bpm / 60.0)))


def _stem_track(stem: str, events: list[MusicalEvent], tempo_bpm: float) -> mido.MidiTrack:
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=stem, time=0))
    channel = STEM_CHANNELS.get(stem, 0)
    note_messages: list[tuple[int, int, mido.Message]] = []

    for event in sorted(events, key=lambda item: float(_value(item, "onset_s", "start_time") or 0.0)):
        pitch = _value(event, "pitch_midi", "midi_pitch")
        if pitch is None or pitch == 0:
            continue
        onset = float(_value(event, "onset_s", "start_time") or 0.0)
        duration = float(_value(event, "duration_s") or 0.0)
        if duration == 0.0:
            end_time = _value(event, "end_time")
            duration = max(0.0, float(end_time) - onset) if end_time is not None else 0.0
        velocity = _value(event, "velocity")
        velocity = DEFAULT_VELOCITY if velocity is None else max(0, min(127, int(velocity)))
        start_tick = _ticks(onset, tempo_bpm)
        end_tick = max(start_tick, _ticks(onset + duration, tempo_bpm))
        note_messages.append((start_tick, 0, mido.Message("note_on", note=int(pitch), velocity=velocity, channel=channel)))
        note_messages.append((end_tick, 1, mido.Message("note_off", note=int(pitch), velocity=0, channel=channel)))

    previous_tick = 0
    for absolute_tick, _, message in sorted(note_messages, key=lambda item: (item[0], item[1])):
        message.time = absolute_tick - previous_tick
        track.append(message)
        previous_tick = absolute_tick
    return track


def export_midi(
    stem_events: dict[str, list[MusicalEvent]], tempo_bpm: float, output_path: Path
) -> Path:
    """Write a tempo track and one MIDI track per stem, returning ``output_path``."""
    if not stem_events:
        raise ValueError("stem_events must not be empty")
    if tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be greater than 0")

    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    midi.tracks.append(tempo_track)
    for stem, events in stem_events.items():
        midi.tracks.append(_stem_track(stem, events, tempo_bpm))
    midi.save(str(output_path))
    return output_path
