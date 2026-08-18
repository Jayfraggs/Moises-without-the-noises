"""
note_extraction.py

Monophonic pitch tracking -> consolidated note-name timeline.

IMPORTANT LIMITATION (read this before trusting the output):
librosa.pyin is a MONOPHONIC pitch tracker. It assumes exactly one note is
sounding at a time. This is a reasonable assumption for an isolated bass or
vocal stem, but it will produce garbage on a stem with chords or multiple
overlapping instruments (e.g. Demucs' "other" stem, which is often piano +
guitar + synth layered together). Callers should not offer note detection
for "other" or "drums" -- this is enforced in main.py, not here, so keep
that in sync if you add more instrument types.

This exact file is duplicated (not imported) into the Colab notebook, since
Colab can't easily import a local backend module. If you change the
extraction or consolidation logic, update both places.
"""

import numpy as np
import librosa

# Reasonable fmin/fmax per instrument type. Widen these if your source
# material has notes outside typical range (e.g. a bass with extended range,
# or a soprano vocal) -- pyin will simply not detect anything outside the
# window you give it.
FREQ_RANGES = {
    "bass": ("C1", "G4"),
    "vocals": ("C2", "C6"),
    "other": ("C2", "C6"),  # usable only if the stem happens to be monophonic
}

# Segments shorter than this (seconds) are almost always pitch-tracker noise
# (a frame or two of octave error, a transient) rather than a real note.
# Merge them into a neighbor rather than showing them as their own note.
MIN_SEGMENT_DURATION = 0.08

# If pyin's estimate jitters by less than this many MIDI semitones between
# consecutive voiced frames, treat it as the same note rather than firing a
# new segment for tracker noise around a note boundary.
NOTE_CHANGE_THRESHOLD_SEMITONES = 0.5


def extract_note_timeline(audio_path: str, instrument: str) -> list[dict]:
    """
    Returns a list of consolidated note segments:
        [{"start": 12.34, "end": 12.81, "note": "A2", "midi": 45}, ...]

    Raises ValueError if `instrument` isn't in FREQ_RANGES -- this is a
    monophonic tracker and we don't want to silently produce nonsense for
    polyphonic material.
    """
    if instrument not in FREQ_RANGES:
        raise ValueError(
            f"No frequency range configured for '{instrument}'. "
            f"Note detection is only meaningful for: {list(FREQ_RANGES.keys())}. "
            f"Drums and polyphonic 'other' stems will produce unreliable results."
        )

    fmin_name, fmax_name = FREQ_RANGES[instrument]
    fmin = librosa.note_to_hz(fmin_name)
    fmax = librosa.note_to_hz(fmax_name)

    y, sr = librosa.load(audio_path, sr=None, mono=True)

    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, fmin=fmin, fmax=fmax, sr=sr
    )
    times = librosa.times_like(f0, sr=sr)

    # Convert frame-by-frame f0 into raw (time, midi) points, dropping
    # unvoiced frames entirely.
    raw_points = []
    for t, f, voiced in zip(times, f0, voiced_flag):
        if voiced and f is not None and not np.isnan(f):
            midi = librosa.hz_to_midi(float(f))
            raw_points.append((float(t), midi))

    if not raw_points:
        return []

    # Consolidate consecutive frames into segments where the MIDI value
    # stays within NOTE_CHANGE_THRESHOLD_SEMITONES of the segment's running
    # average. This absorbs natural pitch tracker jitter and vibrato without
    # merging genuinely different notes.
    segments = []
    seg_start_time = raw_points[0][0]
    seg_midi_values = [raw_points[0][1]]
    prev_time = raw_points[0][0]

    frame_hop = times[1] - times[0] if len(times) > 1 else 0.01
    # If the gap between voiced frames is much larger than one frame hop,
    # treat it as a new segment even if the pitch happens to match --
    # otherwise a held note across a silence would incorrectly bridge.
    gap_threshold = frame_hop * 3

    for t, midi in raw_points[1:]:
        running_avg = sum(seg_midi_values) / len(seg_midi_values)
        pitch_close = abs(midi - running_avg) <= NOTE_CHANGE_THRESHOLD_SEMITONES
        time_contiguous = (t - prev_time) <= gap_threshold

        if pitch_close and time_contiguous:
            seg_midi_values.append(midi)
        else:
            segments.append((seg_start_time, prev_time, seg_midi_values))
            seg_start_time = t
            seg_midi_values = [midi]

        prev_time = t

    segments.append((seg_start_time, prev_time, seg_midi_values))

    # Merge into the previous cleaned segment when either:
    #   (a) this segment is itself too short to be a real note (a 1-2 frame
    #       glitch, regardless of what pitch it glitched to), or
    #   (b) it's the SAME note as the previous segment, separated only by a
    #       small gap -- meaning a brief tracker glitch interrupted an
    #       otherwise continuous held note, and this is really one note,
    #       not two.
    # (b) is the fix for a real bug caught by a synthetic test: without it,
    # a note held through a brief mid-note glitch gets reported as two
    # adjacent segments of the same note with a spurious boundary between
    # them, instead of one continuous segment. The glitch itself gets
    # correctly absorbed by (a) -- what was missing was reuniting the
    # before/after halves of the real note once the glitch was gone.
    # gap_threshold (frame_hop * 3) is reused here rather than
    # MIN_SEGMENT_DURATION so "contiguous enough to merge" uses the same
    # definition as the raw consolidation loop above -- a real rest between
    # two occurrences of the same note (bassist plays A2, rests, plays A2
    # again) should NOT be bridged, and gap_threshold is deliberately tight
    # enough to avoid that.
    cleaned = []
    for seg in segments:
        start, end, midi_values = seg
        duration = end - start
        avg_midi = round(sum(midi_values) / len(midi_values))
        note_name = librosa.midi_to_note(avg_midi)

        if cleaned:
            prev_start, prev_end, prev_note, prev_midi = cleaned[-1]
            gap = start - prev_end
            is_short_glitch = duration < MIN_SEGMENT_DURATION
            is_same_note_reunion = (note_name == prev_note) and (gap <= gap_threshold)

            if is_short_glitch or is_same_note_reunion:
                cleaned[-1] = (prev_start, end, prev_note, prev_midi)
                continue

        cleaned.append((start, end, note_name, avg_midi))

    return [
        {
            "start": round(start, 3),
            "end": round(end, 3),
            "note": note,
            "midi": midi,
        }
        for start, end, note, midi in cleaned
    ]
