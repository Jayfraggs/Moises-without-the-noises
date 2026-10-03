"""
click_render.py — Render click track to audio for exports.

Ported from StemDeck app/pipeline/click_render.py (Apache-2.0).

Playback synthesises the click in the browser (AudioEngine.js metronome).
This module produces an equivalent WAV so the click can be included in
stem exports via ffmpeg. The voice constants are kept identical to the
frontend so monitored and exported clicks match exactly.
"""

from __future__ import annotations

import hashlib
import logging
import wave
from pathlib import Path

logger = logging.getLogger("mwtn.click_render")

# Voice constants — must match AudioEngine.js metronome implementation
CLICK_FREQ   = 1000.0
GROUP_FREQ   = 1225.0
ACCENT_FREQ  = 1500.0
CLICK_DECAY  = 0.035
CLICK_ATTACK = 0.001
CLICK_PEAK   = 0.7
GROUP_PEAK   = 0.85
ACCENT_PEAK  = 1.0

LEVEL_WEAK     = 0
LEVEL_GROUP    = 1
LEVEL_DOWNBEAT = 2
RAMP_FLOOR     = 0.0001

ACCENT_AUTO = -1
ACCENT_OFF  = 0

_VALID_MULTIPLIERS = (0.5, 1.0, 2.0)


def default_grouping(beats_per_bar: int) -> list[int]:
    if beats_per_bar < 1:
        return []
    if beats_per_bar in (5, 7):
        return [3] + [2] * ((beats_per_bar - 3) // 2)
    if beats_per_bar >= 6 and beats_per_bar % 3 == 0:
        return [3] * (beats_per_bar // 3)
    return [beats_per_bar]


def normalise_grouping(groups: list[int] | None, beats_per_bar: int) -> list[int]:
    if beats_per_bar < 1:
        return []
    if not groups:
        return default_grouping(beats_per_bar)
    if not all(isinstance(g, int) and g >= 1 for g in groups):
        return default_grouping(beats_per_bar)
    if sum(groups) != beats_per_bar:
        return default_grouping(beats_per_bar)
    return list(groups)


def group_offsets(groups: list[int]) -> set[int]:
    offsets: set[int] = set()
    at = 0
    for g in groups[:-1]:
        at += g
        offsets.add(at)
    return offsets


def rescale_beats(beats: list[float], multiplier: float) -> list[float]:
    if multiplier == 2.0:
        out: list[float] = []
        for i in range(len(beats) - 1):
            out.append(beats[i])
            out.append((beats[i] + beats[i + 1]) / 2.0)
        if beats:
            out.append(beats[-1])
        return out
    if multiplier == 0.5:
        return beats[::2]
    return list(beats)


def source_index(i: int, multiplier: float) -> int | None:
    if multiplier == 2.0:
        return i // 2 if i % 2 == 0 else None
    if multiplier == 0.5:
        return i * 2
    return i


def _bar_position(index: int, bars: list[dict], accent_mode: int) -> tuple[int, int] | None:
    if accent_mode == ACCENT_OFF:
        return None
    if accent_mode > 0:
        return index % accent_mode, accent_mode
    mark = None
    for b in bars:
        beat = b.get("beat")
        if isinstance(beat, int) and beat <= index:
            mark = b
        else:
            break
    if mark is None:
        return None
    per_bar = mark.get("beats_per_bar")
    if not isinstance(per_bar, int) or per_bar < 1:
        return None
    return (index - mark["beat"]) % per_bar, per_bar


def is_downbeat(index: int | None, bars: list[dict], accent_mode: int) -> bool:
    if index is None:
        return False
    pos = _bar_position(index, bars, accent_mode)
    return pos is not None and pos[0] == 0


def beat_level(
    index: int | None, bars: list[dict], accent_mode: int, groups: list[int] | None = None
) -> int:
    if index is None:
        return LEVEL_WEAK
    pos = _bar_position(index, bars, accent_mode)
    if pos is None:
        return LEVEL_WEAK
    offset, per_bar = pos
    if offset == 0:
        return LEVEL_DOWNBEAT
    if accent_mode > 0:
        bar_groups = normalise_grouping(groups, per_bar)
    else:
        bar_groups = default_grouping(per_bar)
    return LEVEL_GROUP if offset in group_offsets(bar_groups) else LEVEL_WEAK


def count_in_beats_per_bar(bars: list[dict], accent_mode: int, start_index: int = 0) -> int:
    if accent_mode > 0:
        return accent_mode
    mark = None
    for b in bars:
        beat = b.get("beat")
        if isinstance(beat, int) and beat <= start_index:
            mark = b
        else:
            break
    if mark is not None:
        per_bar = mark.get("beats_per_bar")
        if isinstance(per_bar, int) and per_bar >= 1:
            return per_bar
    return 4


def _interval_near(grid: list[float], start: float, span: int) -> float | None:
    if len(grid) < 2:
        return None
    i = 0
    while i < len(grid) and grid[i] < start:
        i += 1
    i = min(i, len(grid) - 2)
    diffs = [grid[k + 1] - grid[k] for k in range(i, min(i + max(1, span), len(grid) - 1))]
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return None
    diffs.sort()
    return diffs[len(diffs) // 2]


def count_in_beats(
    beats: list[float],
    bars: list[dict],
    count_bars: int = 1,
    multiplier: float = 1.0,
    accent_mode: int = ACCENT_AUTO,
    start: float = 0.0,
    groups: list[int] | None = None,
) -> tuple[float, list[tuple[float, int]]]:
    if count_bars < 1:
        return 0.0, []
    grid = rescale_beats([float(b) for b in beats], multiplier)
    start_index = 0
    for k, t in enumerate(beats):
        if t <= start:
            start_index = k
        else:
            break
    bpb = count_in_beats_per_bar(bars, accent_mode, start_index)
    interval = _interval_near(grid, start, bpb)
    if interval is None:
        return 0.0, []
    n = count_bars * bpb
    lead_in = n * interval
    bar_groups = normalise_grouping(groups, bpb) if accent_mode > 0 else default_grouping(bpb)
    starts = group_offsets(bar_groups)
    clicks = []
    for j in range(n):
        offset = j % bpb
        if offset == 0:
            level = LEVEL_DOWNBEAT
        elif offset in starts:
            level = LEVEL_GROUP
        else:
            level = LEVEL_WEAK
        clicks.append((j * interval, level))
    return lead_in, clicks


def cache_key(
    song_id: str,
    beats: list[float],
    bars: list[dict],
    duration: float,
    sample_rate: int,
    multiplier: float,
    accent_mode: int,
    count_in_bars: int = 0,
    include_click: bool = True,
    start: float | None = None,
    end: float | None = None,
    groups: list[int] | None = None,
) -> str:
    grid = hashlib.sha1(
        ("|".join(f"{b:.6f}" for b in beats)).encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    bar_sig = ",".join(f"{b.get('beat')}:{b.get('beats_per_bar')}" for b in bars)
    raw = f"{song_id}|{grid}|{bar_sig}|{duration:.3f}|{sample_rate}|{multiplier}|{accent_mode}"
    if groups:
        raw += f"|g{'+'.join(str(int(g)) for g in groups)}"
    if count_in_bars > 0:
        seg = f"{'' if start is None else f'{start:.3f}'}:{'' if end is None else f'{end:.3f}'}"
        raw += f"|ci{count_in_bars}|clk{int(include_click)}|{seg}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def _voice(peak: float, freq: float, sample_rate: int) -> "object":
    import numpy as np

    n = int(round(CLICK_DECAY * sample_rate))
    t = np.arange(n) / sample_rate
    attack = t <= CLICK_ATTACK
    env = np.empty(n)
    env[attack] = RAMP_FLOOR * (peak / RAMP_FLOOR) ** (t[attack] / CLICK_ATTACK)
    span = CLICK_DECAY - CLICK_ATTACK
    env[~attack] = peak * (RAMP_FLOOR / peak) ** ((t[~attack] - CLICK_ATTACK) / span)
    return np.sin(2.0 * np.pi * freq * t) * env


def _song_click_events(
    beats: list[float],
    bars: list[dict],
    multiplier: float,
    accent_mode: int,
    groups: list[int] | None = None,
) -> list[tuple[float, int]]:
    grid = rescale_beats([float(b) for b in beats], multiplier)
    return [
        (t, beat_level(source_index(i, multiplier), bars, accent_mode, groups))
        for i, t in enumerate(grid)
    ]


def _render_events(
    dest: Path, events: list[tuple[float, int]], duration: float, sample_rate: int
) -> Path | None:
    total = int(round(duration * sample_rate))
    if not events or total <= 0:
        return None

    import numpy as np

    buf = np.zeros(total, dtype=np.float32)
    voices = {
        LEVEL_WEAK:     _voice(CLICK_PEAK,  CLICK_FREQ,  sample_rate),
        LEVEL_GROUP:    _voice(GROUP_PEAK,  GROUP_FREQ,  sample_rate),
        LEVEL_DOWNBEAT: _voice(ACCENT_PEAK, ACCENT_FREQ, sample_rate),
    }

    for t, level in events:
        start = int(round(t * sample_rate))
        if start >= total or start < 0:
            continue
        voice = voices.get(int(level), voices[LEVEL_WEAK])
        n = min(len(voice), total - start)
        buf[start : start + n] += voice[:n]

    np.clip(buf, -1.0, 1.0, out=buf)
    pcm = (buf * 32767.0).astype("<i2")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".wav.tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    tmp.replace(dest)
    return dest


def render_click_wav(
    dest: Path,
    beats: list[float],
    bars: list[dict],
    duration: float,
    sample_rate: int = 44100,
    multiplier: float = 1.0,
    accent_mode: int = ACCENT_AUTO,
    groups: list[int] | None = None,
) -> Path | None:
    """Render the full click track WAV for export mixing."""
    if multiplier not in _VALID_MULTIPLIERS:
        multiplier = 1.0
    events = _song_click_events(beats, bars, multiplier, accent_mode, groups)
    out = _render_events(dest, events, duration, sample_rate)
    if out is not None:
        logger.info("click render: %d events, %.1f s -> %s", len(events), duration, dest.name)
    return out
