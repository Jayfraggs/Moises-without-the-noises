"""Quantize transcription events to a beat grid."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Any, Literal

from backend.audio.duration_mapper import (
    TICKS_PER_BEAT,
    duration_name_to_ticks,
    seconds_to_ticks,
    ticks_to_duration_name,
)
from backend.audio.meter import BeatGrid, BeatGridEntry, TimeSig
from backend.schema.events import NoteEvent, RestEvent

QuantizationMode = Literal["strict", "humanized", "off"]


@dataclass
class QuantizationConfig:
    mode: QuantizationMode = "humanized"
    humanized_tolerance: float = 0.15
    subdivision_resolution: int = 24
    generate_rests: bool = True
    detect_triplets: bool = True
    triplet_tolerance: float = 0.1


@dataclass
class QuantizedPosition:
    measure: int
    beat: int
    subdivision: int
    tick: int


def _normalize_bounds(value: float, lower: float, upper: float) -> float:
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _closest_beat_entry(time_s: float, grid: BeatGrid) -> BeatGridEntry | None:
    if not grid.entries:
        return None
    return min(grid.entries, key=lambda entry: abs(entry.time_s - time_s))


def _measure_and_beat_for_tick(grid: BeatGrid, tick_index: int) -> tuple[int, int, int]:
    if grid.time_sig.numerator <= 0:
        return 1, 1, 0

    ticks_per_measure = grid.time_sig.ticks_per_measure()
    measure = 1 + (tick_index // ticks_per_measure)
    offset_in_measure = tick_index % ticks_per_measure
    beat = 1 + (offset_in_measure // TICKS_PER_BEAT)
    subdivision = offset_in_measure % TICKS_PER_BEAT
    return measure, beat, subdivision


def quantize_time(time_s: float, grid: BeatGrid, config: QuantizationConfig) -> QuantizedPosition | None:
    """Quantize a time to a note-position within the beat grid."""
    if not grid.entries:
        return None

    beat_entry = _closest_beat_entry(time_s, grid)
    if beat_entry is None:
        return None

    offset_s = time_s - beat_entry.time_s
    offset_ticks = seconds_to_ticks(offset_s, beat_entry.tempo_bpm)
    beat_duration_s = 60.0 / max(beat_entry.tempo_bpm, 0.001)

    snap_ticks = int(round(offset_ticks))
    if config.mode == "humanized" and abs(offset_s) <= config.humanized_tolerance * beat_duration_s:
        snap_ticks = 0

    measure_start_tick = ((beat_entry.measure_number - 1) * grid.time_sig.ticks_per_measure())
    beat_start_tick = measure_start_tick + ((beat_entry.beat_in_measure - 1) * TICKS_PER_BEAT)
    absolute_tick = beat_start_tick + snap_ticks

    while absolute_tick < 0:
        absolute_tick += grid.time_sig.ticks_per_measure()
        beat_entry = BeatGridEntry(  # pragma: no cover - protective fallback
            beat_index=beat_entry.beat_index,
            time_s=beat_entry.time_s,
            measure_number=beat_entry.measure_number - 1,
            beat_in_measure=beat_entry.beat_in_measure,
            is_downbeat=beat_entry.is_downbeat,
            tempo_bpm=beat_entry.tempo_bpm,
        )

    measure, beat, subdivision = _measure_and_beat_for_tick(grid, absolute_tick)
    return QuantizedPosition(measure=measure, beat=beat, subdivision=subdivision, tick=int(absolute_tick))


def quantize_event(event: NoteEvent, grid: BeatGrid, config: QuantizationConfig) -> dict:
    """Return quantization metadata to merge into a note event."""
    start_pos = quantize_time(event.start_time, grid, config)
    end_time = event.end_time if event.end_time is not None else event.start_time
    end_pos = quantize_time(end_time, grid, config)

    if start_pos is None or end_pos is None:
        return {
            "quantized_start": None,
            "quantized_end": None,
            "quantized_duration_ticks": 0,
            "quantized_duration_name": "unknown",
            "dotted": False,
            "tuplet": None,
            "tied_from_previous": False,
            "tied_to_next": False,
            "quantization_confidence": 0.0,
            "quantization_mode": config.mode,
        }

    duration_ticks = max(0, end_pos.tick - start_pos.tick)
    duration_name, dotted, tuplet = ticks_to_duration_name(duration_ticks)
    nearest_beat = _closest_beat_entry(event.start_time, grid)
    if nearest_beat is None:
        confidence = 0.0
    else:
        beat_duration = 60.0 / max(nearest_beat.tempo_bpm, 0.001)
        deviation_fraction = abs(event.start_time - nearest_beat.time_s) / max(beat_duration, 1e-9)
        confidence = 1.0 - min(deviation_fraction, 1.0)

    return {
        "quantized_start": {
            "measure": start_pos.measure,
            "beat": start_pos.beat,
            "subdivision": start_pos.subdivision,
            "tick": start_pos.tick,
        },
        "quantized_end": {
            "measure": end_pos.measure,
            "beat": end_pos.beat,
            "subdivision": end_pos.subdivision,
            "tick": end_pos.tick,
        },
        "quantized_duration_ticks": duration_ticks,
        "quantized_duration_name": duration_name,
        "dotted": dotted,
        "tuplet": tuplet,
        "tied_from_previous": False,
        "tied_to_next": False,
        "quantization_confidence": float(_normalize_bounds(confidence, 0.0, 1.0)),
        "quantization_mode": config.mode,
    }


def split_at_barline(event: NoteEvent, grid: BeatGrid, config: QuantizationConfig) -> list[dict]:
    """Split a note event that crosses a measure boundary."""
    start_quant = quantize_time(event.start_time, grid, config)
    end_time = event.end_time if event.end_time is not None else event.start_time
    end_quant = quantize_time(end_time, grid, config)

    if start_quant is None or end_quant is None or start_quant.measure == end_quant.measure:
        return [quantize_event(event, grid, config)]

    range_info = grid.get_measure_range(start_quant.measure)
    if not range_info:
        return [quantize_event(event, grid, config)]

    measure_end_s = range_info[1]
    first_end_s = max(min(measure_end_s, end_time), event.start_time)
    second_start_s = max(first_end_s, event.start_time)

    first_event = NoteEvent(
        track_id=event.track_id,
        start_time=event.start_time,
        end_time=first_end_s,
        midi_pitch=event.midi_pitch,
        confidence=event.confidence,
        source_model=event.source_model,
        duration_s=first_end_s - event.start_time,
        frequency_hz=event.frequency_hz,
        velocity=event.velocity,
        pitch_confidence=event.pitch_confidence,
    )
    second_event = NoteEvent(
        track_id=event.track_id,
        start_time=second_start_s,
        end_time=end_time,
        midi_pitch=event.midi_pitch,
        confidence=event.confidence,
        source_model=event.source_model,
        duration_s=end_time - second_start_s,
        frequency_hz=event.frequency_hz,
        velocity=event.velocity,
        pitch_confidence=event.pitch_confidence,
    )

    first_quant = quantize_event(first_event, grid, config)
    second_quant = quantize_event(second_event, grid, config)
    first_quant["tied_to_next"] = True
    second_quant["tied_from_previous"] = True
    return [first_quant, second_quant]


def detect_triplets(events: list[NoteEvent], grid: BeatGrid, config: QuantizationConfig) -> list[int]:
    """Return indices of events in triplet groups."""
    if len(events) < 3:
        return []

    ordered = sorted(events, key=lambda ev: ev.start_time)
    triplet_indices: set[int] = set()

    for i in range(len(ordered) - 2):
        slice_events = ordered[i : i + 3]
        if len(slice_events) < 3:
            continue

        positions = [quantize_time(ev.start_time, grid, config) for ev in slice_events]
        if any(pos is None for pos in positions):
            continue

        start_times = [ev.start_time for ev in slice_events]
        gaps = [b - a for a, b in zip(start_times, start_times[1:])]
        if not gaps or any(g <= 0 for g in gaps):
            continue

        beat_duration = 60.0 / max(grid.entries[0].tempo_bpm, 0.001) if grid.entries else 0.5
        expected_gap = beat_duration / 3.0
        gap_tolerance = config.triplet_tolerance * beat_duration / 2.0
        if any(not isclose(gap, expected_gap, abs_tol=gap_tolerance) for gap in gaps):
            continue

        total_duration = sum((ev.end_time if ev.end_time is not None else ev.start_time) - ev.start_time for ev in slice_events)
        if not isclose(total_duration, beat_duration, abs_tol=config.triplet_tolerance * beat_duration):
            continue

        triplet_indices.update({ordered.index(ev) for ev in slice_events})

    return sorted(triplet_indices)


def generate_rests(events: list[NoteEvent], grid: BeatGrid) -> list[RestEvent]:
    """Generate rest events for gaps between adjacent note events on the same track."""
    rests: list[RestEvent] = []
    ordered = sorted(events, key=lambda ev: ev.start_time)

    for prev, nxt in zip(ordered, ordered[1:]):
        if prev.track_id != nxt.track_id:
            continue

        prev_end = prev.end_time if prev.end_time is not None else prev.start_time
        gap_s = nxt.start_time - prev_end
        if gap_s <= 0:
            continue

        gap_ticks = seconds_to_ticks(gap_s, max(grid.entries[0].tempo_bpm, 1.0)) if grid.entries else 0
        if gap_ticks < 1:
            continue

        rest = RestEvent(
            track_id=prev.track_id,
            start_time=prev_end,
            end_time=nxt.start_time,
            confidence=1.0,
            source_model="quantizer",
            duration_s=gap_s,
        )
        rests.append(rest)

    return rests


def validate_measure(measure_events: list, time_sig: TimeSig) -> dict:
    """Validate that a measure adds up to the expected duration."""
    total_ticks = 0
    for item in measure_events:
        if isinstance(item, dict):
            duration_ticks = item.get("quantized_duration_ticks")
            if duration_ticks is None:
                if "duration_s" in item:
                    duration_ticks = seconds_to_ticks(float(item["duration_s"]), 120.0)
                else:
                    continue
            total_ticks += int(duration_ticks)
        elif hasattr(item, "duration_s"):
            duration_ticks = getattr(item, "duration_s", 0.0)
            total_ticks += int(seconds_to_ticks(float(duration_ticks), 120.0))

    expected_ticks = time_sig.ticks_per_measure()
    valid = total_ticks == expected_ticks
    error = None if valid else f"Measure total {total_ticks} ticks does not match expected {expected_ticks} ticks."
    return {
        "valid": bool(valid),
        "total_ticks": int(total_ticks),
        "expected_ticks": int(expected_ticks),
        "error": error,
    }


def quantize_events(
    events: list[NoteEvent],
    grid: BeatGrid,
    config: QuantizationConfig | None = None,
) -> list[dict]:
    """Quantize all note events and return merged event dictionaries."""
    if config is None:
        config = QuantizationConfig()

    if not events:
        return []

    ordered_events = sorted(events, key=lambda ev: ev.start_time)
    quantized_results: list[dict] = []

    for event in ordered_events:
        quantized = quantize_event(event, grid, config)
        merged = event.model_dump(mode="json")
        merged.update(quantized)
        quantized_results.append(merged)

    if config.detect_triplets:
        triplet_indices = detect_triplets(ordered_events, grid, config)
        for idx in triplet_indices:
            if idx < len(quantized_results):
                quantized_results[idx]["tuplet"] = "triplet"

    if config.generate_rests:
        rests = generate_rests(ordered_events, grid)
        for rest in rests:
            rest_payload = rest.model_dump(mode="json")
            rest_payload["quantized_start"] = {
                "measure": 1,
                "beat": 1,
                "subdivision": 0,
                "tick": 0,
            }
            rest_payload["quantized_end"] = {
                "measure": 1,
                "beat": 1,
                "subdivision": 0,
                "tick": 0,
            }
            rest_payload["quantized_duration_ticks"] = 0
            rest_payload["quantized_duration_name"] = "rest"
            rest_payload["dotted"] = False
            rest_payload["tuplet"] = None
            rest_payload["tied_from_previous"] = False
            rest_payload["tied_to_next"] = False
            rest_payload["quantization_confidence"] = 1.0
            rest_payload["quantization_mode"] = config.mode
            quantized_results.append(rest_payload)

    quantized_results.sort(key=lambda item: item.get("quantized_start", {}).get("tick", item.get("start_time", 0)))

    measures: dict[int, list[dict]] = {}
    for item in quantized_results:
        key = item.get("quantized_start", {}).get("measure")
        if key is None:
            continue
        measures.setdefault(int(key), []).append(item)

    for measure_number, items in measures.items():
        validation = validate_measure(items, grid.time_sig)
        for item in items:
            item["measure_validation"] = validation

    return quantized_results


__all__ = [
    "QuantizationConfig",
    "QuantizedPosition",
    "QuantizationMode",
    "quantize_time",
    "quantize_event",
    "split_at_barline",
    "detect_triplets",
    "generate_rests",
    "validate_measure",
    "quantize_events",
]
