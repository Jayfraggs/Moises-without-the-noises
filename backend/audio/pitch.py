"""
pitch.py — Pitch shifting via librosa (offline/server-side).

This is for the export path: if the user wants to download a stem
transposed by N semitones, we process it here and return a WAV.

For REAL-TIME pitch shifting during playback, this is NOT the right
module — that needs to happen in the browser via Web Audio API /
AudioWorklet. See frontend/src/AudioEngine.js for the playback side.

librosa.effects.pitch_shift uses a phase vocoder under the hood.
Quality is decent for small shifts (±6 semitones); larger shifts
introduce artifacts, especially on vocals. This is a known limitation
of phase vocoders vs. more sophisticated time-domain methods (e.g.
Rubber Band Library), but librosa is zero-dependency and good enough
for a v1.

Speed-without-pitch-change (time stretching) is also here:
librosa.effects.time_stretch. Same phase vocoder, same trade-offs.
"""

import io
import json
import warnings
from math import ceil

import librosa
import soundfile as sf
import numpy as np


STEM_PYIN_CONFIG = {
    "bass":   {"fmin": librosa.note_to_hz("B0"),
               "fmin_safe": librosa.note_to_hz("E1"),
               "fmax": librosa.note_to_hz("G3"),
               "frame_length": 4096},
    "vocals": {"fmin": librosa.note_to_hz("C2"),
               "fmax": librosa.note_to_hz("C6"),
               "frame_length": 2048},
    "guitar": {"fmin": librosa.note_to_hz("E2"),
               "fmax": librosa.note_to_hz("E6"),
               "frame_length": 2048},
    "piano":  {"fmin": librosa.note_to_hz("A0"),
               "fmin_safe": librosa.note_to_hz("C2"),
               "fmax": librosa.note_to_hz("C8"),
               "frame_length": 4096},
    "other":  {"fmin": librosa.note_to_hz("C2"),
               "fmax": librosa.note_to_hz("C7"),
               "frame_length": 2048},
    "drums":  None,
}


def _resolve_stem_config(stem: str):
    default = {"fmin": librosa.note_to_hz("C2"),
               "fmax": librosa.note_to_hz("C6"),
               "frame_length": 2048}
    cfg = STEM_PYIN_CONFIG.get(stem, None)
    if cfg is None and stem not in STEM_PYIN_CONFIG:
        return default
    return cfg


def extract_notes_from_file(audio_path: str,
                            stem: str,
                            out_json_path: str = None,
                            voiced_prob_threshold: float = 0.6,
                            min_duration_s: float = 0.08,
                            hop_length: int = 512):
    """
    Extracts note segments from `audio_path` for the given `stem` and writes
    notes to `out_json_path` (or `notes_<stem>.json` by default).

    Returns the list of note dicts: {note, start, end, confidence}.
    """
    if out_json_path is None:
        out_json_path = f"notes_{stem}.json"

    # Load and convert to mono for pyin
    y, sr = librosa.load(audio_path, sr=None, mono=False)
    if y.ndim > 1:
        y_mono = librosa.to_mono(y)
    else:
        y_mono = y

    cfg = STEM_PYIN_CONFIG.get(stem, None)
    if cfg is None:
        # Config explicitly None (e.g., drums) -> write empty and return
        if stem in STEM_PYIN_CONFIG and STEM_PYIN_CONFIG[stem] is None:
            with open(out_json_path, "w", encoding="utf-8") as fh:
                json.dump([], fh)
            print(f"[pitch] stem='{stem}' skipped (pyin not applicable). Wrote empty {out_json_path}.")
            return []
        # Else fall back to defaults
        cfg = {"fmin": librosa.note_to_hz("C2"),
               "fmax": librosa.note_to_hz("C6"),
               "frame_length": 2048}

    # Use fmin_safe if present to avoid librosa's pyin UserWarning
    fmin_pass = cfg.get("fmin_safe", cfg.get("fmin"))
    fmax = cfg.get("fmax")
    frame_length = cfg.get("frame_length", 2048)

    # Log adjustment
    if "fmin_safe" in cfg:
        print(f"[pitch] stem='{stem}': using fmin_safe={fmin_pass:.2f}Hz instead of fmin={cfg.get('fmin'):.2f}Hz")

    # Call pyin while suppressing only the fmin/frame_length UserWarning
    f0 = None
    voiced_flag = None
    voiced_probs = None
    warn_msg_re = r".*fmin.*frame_length.*|.*pyin.*fmin.*"
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=warn_msg_re, category=UserWarning)
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y_mono,
            fmin=fmin_pass,
            fmax=fmax,
            sr=sr,
            frame_length=frame_length,
            hop_length=hop_length,
        )

    # voiced_probs may be None in some librosa versions; guard
    if voiced_probs is None:
        voiced_probs = np.where(voiced_flag, 1.0, 0.0)

    # Apply voiced probability gate
    voiced_mask = voiced_probs >= voiced_prob_threshold

    # Convert boolean mask to contiguous segments and apply min-duration gate
    frame_duration = hop_length / float(sr)
    min_frames = max(1, ceil(min_duration_s / frame_duration))

    segments = []
    n_frames = len(voiced_mask)
    i = 0
    while i < n_frames:
        if not voiced_mask[i]:
            i += 1
            continue
        j = i
        while j < n_frames and voiced_mask[j]:
            j += 1
        length = j - i
        if length >= min_frames:
            segments.append((i, j))
        i = j

    print(f"[pitch] stem='{stem}': {len(segments)} segments after gating (min_frames={min_frames}).")

    notes = []
    for (start_f, end_f) in segments:
        # Select f0 values in this segment that are finite
        f0_seg = f0[start_f:end_f]
        valid_idx = np.isfinite(f0_seg)
        if not np.any(valid_idx):
            # fallback if no f0 estimate: skip
            continue
        median_hz = float(np.median(f0_seg[valid_idx]))
        note_name = librosa.hz_to_note(median_hz)
        conf = float(np.mean(voiced_probs[start_f:end_f]))
        start_t = start_f * frame_duration
        end_t = end_f * frame_duration
        notes.append({"note": note_name, "start": start_t, "end": end_t, "confidence": conf})

    # Write JSON
    with open(out_json_path, "w", encoding="utf-8") as fh:
        json.dump(notes, fh)

    return notes


def pitch_shift_wav(audio_path: str, semitones: float) -> bytes:
    """
    Returns WAV bytes of the audio shifted by `semitones` semitones.
    Positive = up, negative = down. Range: -12 to +12 recommended.
    """
    y, sr = librosa.load(audio_path, sr=None, mono=False)

    # librosa.effects.pitch_shift expects mono or (channels, samples).
    # If stereo (2D), process each channel independently to avoid the
    # "too many dimensions" error.
    if y.ndim == 1:
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)
    else:
        y_shifted = np.stack([
            librosa.effects.pitch_shift(ch, sr=sr, n_steps=semitones)
            for ch in y
        ])

    buf = io.BytesIO()
    sf.write(buf, y_shifted.T if y_shifted.ndim > 1 else y_shifted, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def time_stretch_wav(audio_path: str, rate: float) -> bytes:
    """
    Returns WAV bytes time-stretched by `rate` without changing pitch.
    rate > 1.0 = faster, rate < 1.0 = slower.
    Range: 0.5–2.0 recommended; outside that, artifact quality degrades.
    """
    y, sr = librosa.load(audio_path, sr=None, mono=False)

    if y.ndim == 1:
        y_stretched = librosa.effects.time_stretch(y, rate=rate)
    else:
        y_stretched = np.stack([
            librosa.effects.time_stretch(ch, rate=rate)
            for ch in y
        ])

    buf = io.BytesIO()
    sf.write(buf, y_stretched.T if y_stretched.ndim > 1 else y_stretched, sr, format="WAV")
    buf.seek(0)
    return buf.read()
