"""
sections.py — Song-section schema, normalizer, and validator.

Ported from StemDeck (app/pipeline/sections.py, MIT licence).
The inference model (allin1/harmonix) is NOT included here — this
module handles only schema normalisation so the backend can store,
serve, and validate section data from any source (Colab pipeline,
manual editor, future model integration).

normalize_sections() is the entry point: it takes untrusted model or
user output and returns a clean, gap-free list of section records, or
[] if the input cannot be made valid.
"""

from __future__ import annotations

import math
from numbers import Real

_KINDS = frozenset(("intro", "outro", "break", "bridge", "inst", "solo",
                    "verse", "chorus", "part"))
_SENTINELS = frozenset(("start", "end"))
_NEUTRAL_KIND = "part"

SECTION_NAMES = {
    "intro": "Intro",
    "outro": "Outro",
    "break": "Break",
    "bridge": "Bridge",
    "inst": "Instrumental",
    "solo": "Solo",
    "verse": "Verse",
    "chorus": "Chorus",
    "part": "Part",
}

SECTION_COLORS = {
    "intro": "#4a7fff",
    "verse": "#00c8a0",
    "chorus": "#9a4aff",
    "bridge": "#ff8a20",
    "break": "#2ab8e8",
    "inst": "#e8c840",
    "solo": "#ff4a90",
    "outro": "#00d4d4",
    "part": "#8391a5",
}

_MIN_SECTION_SECONDS = 0.5
_BOUNDARY_TOLERANCE_SECONDS = 0.25


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _raw_segments(raw: object) -> list | None:
    if isinstance(raw, dict):
        raw = raw.get("segments")
    return raw if isinstance(raw, list) else None


def _merge_short(segments: list[dict]) -> list[dict]:
    result = list(segments)
    while True:
        short_index = next(
            (i for i, s in enumerate(result)
             if float(s["end"]) - float(s["start"]) < _MIN_SECTION_SECONDS),
            None,
        )
        if short_index is None:
            return result
        if len(result) <= 2:
            return []
        i = short_index
        if 0 < i < len(result) - 1 and result[i - 1]["kind"] == result[i + 1]["kind"]:
            result[i - 1]["end"] = result[i + 1]["end"]
            del result[i: i + 2]
        elif i > 0:
            result[i - 1]["end"] = result[i]["end"]
            del result[i]
        else:
            result[i + 1]["start"] = result[i]["start"]
            del result[i]


def normalize_sections(raw_segments: object, duration: float) -> list[dict]:
    """
    Convert untrusted section data into a clean, gap-free list.
    Returns [] if the input cannot be made valid.
    Each record: {id, name, kind, start, end, color}
    """
    duration_value = _number(duration)
    raw = _raw_segments(raw_segments) if not isinstance(raw_segments, list) else raw_segments
    if raw is None:
        raw = raw_segments if isinstance(raw_segments, list) else []

    if duration_value is None or duration_value < 2 * _MIN_SECTION_SECONDS or not raw:
        return []

    parsed: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            return []
        label = item.get("label", item.get("kind"))
        if not isinstance(label, str):
            return []
        kind = label.strip().lower()
        if kind not in _KINDS | _SENTINELS:
            return []
        start = _number(item.get("start"))
        end = _number(item.get("end"))
        if start is None or end is None or end <= start:
            return []
        start = max(0.0, min(duration_value, start))
        end = max(0.0, min(duration_value, end))
        if end <= start:
            continue
        parsed.append({"start": start, "end": end, "kind": kind})

    parsed.sort(key=lambda s: (float(s["start"]), float(s["end"])))

    lo, hi = 0, len(parsed)
    while lo < hi and parsed[lo]["kind"] in _SENTINELS:
        lo += 1
    while hi > lo and parsed[hi - 1]["kind"] in _SENTINELS:
        hi -= 1
    for seg in parsed[lo:hi]:
        if seg["kind"] in _SENTINELS:
            seg["kind"] = _NEUTRAL_KIND

    for left, right in zip(parsed, parsed[1:], strict=False):
        delta = float(right["start"]) - float(left["end"])
        if abs(delta) > _BOUNDARY_TOLERANCE_SECONDS:
            return []
        boundary = (float(left["end"]) + float(right["start"])) / 2
        left["end"] = boundary
        right["start"] = boundary

    meaningful = [s for s in parsed[lo:hi] if s["kind"] in _KINDS]
    if len(meaningful) < 2:
        return []
    meaningful[0]["start"] = 0.0
    meaningful[-1]["end"] = duration_value
    meaningful = _merge_short(meaningful)
    if len(meaningful) < 2:
        return []

    sections: list[dict] = []
    for index, seg in enumerate(meaningful, start=1):
        kind = str(seg["kind"])
        start = round(float(seg["start"]), 3)
        end = round(float(seg["end"]), 3)
        if end - start < _MIN_SECTION_SECONDS:
            return []
        sections.append({
            "id": f"auto-{index:03d}",
            "name": SECTION_NAMES[kind],
            "kind": kind,
            "start": start,
            "end": end,
            "color": SECTION_COLORS[kind],
        })
    return sections


def validate_sections(raw: list, duration: float | None = None) -> list[dict]:
    """
    Validate and normalise a user-supplied section list.
    Raises ValueError with a descriptive message if invalid.
    """
    if not raw:
        raise ValueError("Section list is empty")
    if duration is None:
        try:
            duration = max(float(s.get("end", 0)) for s in raw if isinstance(s, dict))
        except (ValueError, TypeError):
            raise ValueError("Cannot determine duration from section data")
    result = normalize_sections(raw, duration)
    if not result:
        raise ValueError(
            "Section data could not be normalised. Check that each section has "
            "start < end, kind is one of intro/verse/chorus/bridge/break/inst/solo/outro/part, "
            "and adjacent sections do not overlap by more than 0.25 s."
        )
    return result
