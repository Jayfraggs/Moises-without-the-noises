"""MusicXML export from canonical musical events."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Protocol


class MusicalEvent(Protocol):
    """Minimum event attributes consumed by the MusicXML exporter."""

    onset_s: float
    duration_s: float
    pitch_midi: int | None
    duration_beats: float


LOGGER = logging.getLogger(__name__)
DIVISIONS = 4
MEASURE_DURATIONS = {
    4.0: ("whole", 16, 0),
    3.0: ("half", 12, 1),
    2.0: ("half", 8, 0),
    1.5: ("quarter", 6, 1),
    1.0: ("quarter", 4, 0),
    0.75: ("eighth", 3, 1),
    0.5: ("eighth", 2, 0),
    0.25: ("16th", 1, 0),
}
PITCHES = (("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
           ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0))
KEY_FIFTHS = {
    "c": 0, "g": 1, "d": 2, "a": 3, "e": 4, "b": 5, "f#": 6, "c#": 7,
    "f": -1, "bb": -2, "eb": -3, "ab": -4, "db": -5, "gb": -6, "cb": -7,
}


def _get(event: Any, name: str, legacy_name: str | None = None) -> Any:
    value = getattr(event, name, None)
    return getattr(event, legacy_name, None) if value is None and legacy_name else value


def _duration_info(beats: float) -> tuple[str, int, int]:
    if beats <= 0:
        return MEASURE_DURATIONS[1.0]
    nearest = min(MEASURE_DURATIONS, key=lambda value: abs(value - beats))
    return MEASURE_DURATIONS[nearest]


def _duration_beats(event: Any, tempo_bpm: float) -> float:
    value = _get(event, "duration_beats")
    if value is not None:
        return float(value)
    LOGGER.warning("Musical event lacks duration_beats; falling back to duration_s")
    duration_s = float(_get(event, "duration_s") or 0.0)
    return duration_s * tempo_bpm / 60.0


def _append_note(parent: ET.Element, event: Any | None, beats: float) -> None:
    note = ET.SubElement(parent, "note")
    pitch = _get(event, "pitch_midi", "midi_pitch") if event is not None else None
    if pitch is None or pitch == 0:
        ET.SubElement(note, "rest")
    else:
        step, alter = PITCHES[int(pitch) % 12]
        pitch_element = ET.SubElement(note, "pitch")
        ET.SubElement(pitch_element, "step").text = step
        if alter:
            ET.SubElement(pitch_element, "alter").text = str(alter)
        ET.SubElement(pitch_element, "octave").text = str(int(pitch) // 12 - 1)
    note_type, duration, dots = _duration_info(beats)
    ET.SubElement(note, "duration").text = str(duration)
    ET.SubElement(note, "type").text = note_type
    for _ in range(dots):
        ET.SubElement(note, "dot")


def _append_attributes(measure: ET.Element, key_tonic: str, mode: str, time_signature: tuple[int, int]) -> None:
    attributes = ET.SubElement(measure, "attributes")
    ET.SubElement(attributes, "divisions").text = str(DIVISIONS)
    key = ET.SubElement(attributes, "key")
    ET.SubElement(key, "fifths").text = str(max(-7, min(7, KEY_FIFTHS.get(key_tonic.strip().lower(), 0))))
    ET.SubElement(key, "mode").text = mode.lower()
    time = ET.SubElement(attributes, "time")
    ET.SubElement(time, "beats").text = str(time_signature[0])
    ET.SubElement(time, "beat-type").text = str(time_signature[1])
    clef = ET.SubElement(attributes, "clef")
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"


def export_musicxml(
    stem_events: dict[str, list[MusicalEvent]],
    tempo_bpm: float,
    key_tonic: str,
    mode: str,
    time_signature: tuple[int, int],
    output_path: Path,
) -> Path:
    """Write one MusicXML part per stem and return ``output_path``."""
    if not stem_events:
        raise ValueError("stem_events must not be empty")
    if tempo_bpm <= 0 or time_signature[0] <= 0 or time_signature[1] <= 0:
        raise ValueError("tempo and time signature values must be greater than 0")

    measure_beats = time_signature[0] * 4.0 / time_signature[1]
    root = ET.Element("score-partwise", version="4.0")
    part_list = ET.SubElement(root, "part-list")
    for index, stem in enumerate(stem_events, 1):
        score_part = ET.SubElement(part_list, "score-part", id=f"P{index}")
        ET.SubElement(score_part, "part-name").text = stem

    for index, (stem, events) in enumerate(stem_events.items(), 1):
        part = ET.SubElement(root, "part", id=f"P{index}")
        measure_number = 1
        measure = ET.SubElement(part, "measure", number=str(measure_number))
        _append_attributes(measure, key_tonic, mode, time_signature)
        used = 0.0
        for event in sorted(events, key=lambda item: float(_get(item, "onset_s", "start_time") or 0.0)):
            duration = _duration_beats(event, tempo_bpm)
            remaining = max(0.0, duration)
            while remaining > 0:
                available = measure_beats - used
                chunk = min(remaining, available)
                _append_note(measure, event, chunk)
                used += chunk
                remaining -= chunk
                if used >= measure_beats - 1e-9:
                    measure_number += 1
                    measure = ET.SubElement(part, "measure", number=str(measure_number))
                    used = 0.0
        if used > 1e-9:
            _append_note(measure, None, measure_beats - used)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output_path, encoding="unicode", xml_declaration=True)
    return output_path
