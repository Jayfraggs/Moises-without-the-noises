"""Duration lookup helpers for tick-based musical timing."""

from __future__ import annotations

TICKS_PER_BEAT = 24
TICKS_PER_WHOLE = 4 * TICKS_PER_BEAT

DURATION_TABLE: list[tuple[int, str, bool]] = [
    (96, "whole", False),
    (72, "half", True),
    (48, "half", False),
    (36, "quarter", True),
    (24, "quarter", False),
    (18, "eighth", True),
    (12, "eighth", False),
    (9, "sixteenth", True),
    (6, "sixteenth", False),
    (3, "thirty-second", False),
]

TRIPLET_TABLE: list[tuple[int, str, str]] = [
    (32, "quarter", "triplet"),
    (16, "eighth", "triplet"),
    (8, "sixteenth", "triplet"),
]

VALID_DURATIONS: tuple[tuple[str, bool, str | None], ...] = tuple(
    (name, dotted, None) for _, name, dotted in DURATION_TABLE
) + tuple(
    (name, False, tuplet) for _, name, tuplet in TRIPLET_TABLE
)


def ticks_to_duration_name(
    ticks: int, tolerance: int = 0
) -> tuple[str, bool, str | None]:
    """
    Map a tick count to (duration_name, dotted, tuplet_type).
    tuplet_type is None for normal durations, "triplet" for triplets.
    tolerance: accept a tick count within ±tolerance of a table entry. The
    default is strict so unsupported values are not silently quantized.
    Returns ("unknown", False, None) if no match found.
    """
    try:
        tick_count = int(ticks)
    except (TypeError, ValueError):
        return ("unknown", False, None)

    normalized_tolerance = max(0, tolerance)

    # Triplet ticks can overlap with a nearby dotted duration (8 and 9 ticks).
    # Prefer exact matches so the table round-trips without losing tuplets.
    for entry_ticks, name, tuplet in TRIPLET_TABLE:
        if tick_count == entry_ticks:
            return name, False, tuplet

    for entry_ticks, name, dotted in DURATION_TABLE:
        if abs(tick_count - entry_ticks) <= normalized_tolerance:
            return name, dotted, None

    for entry_ticks, name, tuplet in TRIPLET_TABLE:
        if abs(tick_count - entry_ticks) <= normalized_tolerance:
            return name, False, tuplet

    return ("unknown", False, None)


def duration_name_to_ticks(name: str, dotted: bool = False, tuplet: str | None = None) -> int:
    """
    Inverse lookup: name → tick count.
    Raises ValueError if name not found.
    """
    if name is None:
        raise ValueError("Unknown duration name: None. Valid names: whole, half, quarter, eighth, sixteenth, thirty-second, triplet")

    normalized_name = str(name).strip().lower()
    normalized_tuplet = None if tuplet is None else str(tuplet).strip().lower()

    if normalized_tuplet not in (None, "triplet"):
        valid = ", ".join(
            [
                "whole",
                "half",
                "quarter",
                "eighth",
                "sixteenth",
                "thirty-second",
                "quarter triplet",
                "eighth triplet",
                "sixteenth triplet",
            ]
        )
        raise ValueError(f"Unknown duration name {name!r} with tuplet {tuplet!r}. Valid names: {valid}")

    lookup: dict[tuple[str, bool, str | None], int] = {
        ("whole", False, None): 96,
        ("half", False, None): 48,
        ("half", True, None): 72,
        ("quarter", False, None): 24,
        ("quarter", True, None): 36,
        ("eighth", False, None): 12,
        ("eighth", True, None): 18,
        ("sixteenth", False, None): 6,
        ("sixteenth", True, None): 9,
        ("thirty-second", False, None): 3,
        ("quarter", False, "triplet"): 32,
        ("eighth", False, "triplet"): 16,
        ("sixteenth", False, "triplet"): 8,
    }

    key = (normalized_name, bool(dotted), normalized_tuplet)
    if key in lookup:
        return lookup[key]

    valid_names = [
        "whole",
        "half",
        "half (dotted)",
        "quarter",
        "quarter (dotted)",
        "eighth",
        "eighth (dotted)",
        "sixteenth",
        "sixteenth (dotted)",
        "thirty-second",
        "quarter triplet",
        "eighth triplet",
        "sixteenth triplet",
    ]
    raise ValueError(f"Unknown duration name {name!r}. Valid names: {', '.join(valid_names)}")


def ticks_to_quarter_length(ticks: int) -> float:
    """Convert tick count to music21 quarterLength float (quarter = 1.0)."""
    return ticks / TICKS_PER_BEAT


def quarter_length_to_ticks(ql: float) -> int:
    """Convert music21 quarterLength to tick count. Rounds to nearest tick."""
    return round(ql * TICKS_PER_BEAT)


def seconds_to_ticks(duration_s: float, tempo_bpm: float) -> int:
    """Convert a duration in seconds to ticks at a given tempo."""
    if tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be greater than 0 for tick conversion")
    beats = duration_s * (tempo_bpm / 60.0)
    return round(beats * TICKS_PER_BEAT)


def ticks_to_seconds(ticks: int, tempo_bpm: float) -> float:
    """Convert tick count to seconds at a given tempo."""
    if tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be greater than 0 for tick conversion")
    beats = ticks / TICKS_PER_BEAT
    return beats * (60.0 / tempo_bpm)


__all__ = [
    "TICKS_PER_BEAT",
    "TICKS_PER_WHOLE",
    "DURATION_TABLE",
    "TRIPLET_TABLE",
    "ticks_to_duration_name",
    "duration_name_to_ticks",
    "ticks_to_quarter_length",
    "quarter_length_to_ticks",
    "seconds_to_ticks",
    "ticks_to_seconds",
]
