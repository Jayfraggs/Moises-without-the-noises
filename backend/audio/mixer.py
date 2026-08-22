"""
mixer.py

Provides `mix_stems` to read per-song stem WAVs, apply per-stem gains,
optionally synthesize a click track from beat timestamps, and return a
normalized stereo float32 numpy array ready for encoding to WAV.

This module is importable standalone (no FastAPI imports).
"""
from pathlib import Path
from typing import Dict, List

import numpy as np
import soundfile as sf
import librosa


def _ensure_stereo(arr: np.ndarray) -> np.ndarray:
    # arr is (n, channels)
    if arr.ndim == 1:
        arr = arr[:, None]
    channels = arr.shape[1]
    if channels == 1:
        return np.repeat(arr, 2, axis=1)
    if channels >= 2:
        return arr[:, :2]
    return arr


def mix_stems(song_dir: Path, stem_gains: Dict[str, float], include_click: bool, beats: List[float], bpm: float) -> np.ndarray:
    """
    Mix stems found in `song_dir`.

    Args:
        song_dir: Path to the song directory containing stem WAVs and manifest.json.
        stem_gains: map of stem name -> gain (0.0 = mute). Missing keys default to 1.0.
        include_click: whether to synthesize and overlay a click at beat times.
        beats: list of beat timestamps in seconds.
        bpm: tempo estimate (unused by synth but included for API compatibility).

    Returns:
        stereo float32 numpy array shape (n_samples, 2) normalized to [-1.0, 1.0].
    """
    manifest_path = song_dir / "manifest.json"
    if manifest_path.exists():
        try:
            import json

            manifest = json.loads(manifest_path.read_text())
            stem_list = manifest.get("stems", [])
        except Exception:
            stem_list = []
    else:
        stem_list = []

    # Fallback: discover .wav files in the directory (take filename stem)
    if not stem_list:
        stem_list = [p.stem for p in sorted(song_dir.glob("*.wav"))]

    ref_sr = None
    stem_arrays = {}

    # Load each stem, resample if necessary, and convert to stereo
    for stem in stem_list:
        path = song_dir / f"{stem}.wav"
        if not path.exists():
            continue

        data, sr = sf.read(str(path), always_2d=True)
        # soundfile returns shape (frames, channels)
        data = np.asarray(data, dtype=np.float32)

        if ref_sr is None:
            ref_sr = sr

        if sr != ref_sr:
            # resample each channel separately
            ch_count = data.shape[1]
            resampled = []
            for c in range(ch_count):
                resampled_chan = librosa.resample(data[:, c], orig_sr=sr, target_sr=ref_sr)
                resampled.append(resampled_chan)
            data = np.stack(resampled, axis=1)

        data = _ensure_stereo(data)

        gain = float(stem_gains.get(stem, 1.0))
        if gain == 0.0:
            data = np.zeros_like(data, dtype=np.float32)
        else:
            data = data * gain

        stem_arrays[stem] = data

    if ref_sr is None:
        # no stems loaded, return empty array
        return np.zeros((0, 2), dtype=np.float32)

    # Determine mix length (max length of stems)
    max_len = max((arr.shape[0] for arr in stem_arrays.values()), default=0)

    mix = np.zeros((max_len, 2), dtype=np.float32)

    for arr in stem_arrays.values():
        length = arr.shape[0]
        mix[:length, :] += arr

    # Click synthesis
    if include_click and beats:
        freq = 1000.0
        dur = 0.02
        click_len = int(np.ceil(dur * ref_sr))
        if click_len < 1:
            click_len = 1
        t = np.linspace(0, dur, click_len, endpoint=False)
        click = 0.7 * np.sin(2 * np.pi * freq * t).astype(np.float32)
        # apply a short Hann window to avoid sharp edges
        if click_len > 2:
            win = np.hanning(click_len).astype(np.float32)
            click *= win
        click_stereo = np.repeat(click[:, None], 2, axis=1)

        # extend mix if needed
        last_beat = int(np.ceil((beats[-1] + dur) * ref_sr)) if beats else 0
        if last_beat > mix.shape[0]:
            extra = np.zeros((last_beat - mix.shape[0], 2), dtype=np.float32)
            mix = np.vstack([mix, extra])

        for b in beats:
            idx = int(round(b * ref_sr))
            if idx < 0:
                continue
            end = idx + click_len
            if end > mix.shape[0]:
                # extend again
                extra = np.zeros((end - mix.shape[0], 2), dtype=np.float32)
                mix = np.vstack([mix, extra])
            mix[idx:end, :] += click_stereo

    # Normalize to [-1,1]
    max_abs = float(np.max(np.abs(mix))) if mix.size else 0.0
    if max_abs > 0:
        mix = mix / max_abs

    # Ensure float32
    return mix.astype(np.float32)
