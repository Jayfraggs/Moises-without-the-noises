"""
bpm.py — Beat & tempo detection using librosa.

Returns BPM and a list of beat timestamps (seconds). These are used by
the frontend to drive the smart metronome click track and sync the
beat visualizer.

librosa.beat.beat_track is the workhorse here. It uses a combination of
onset detection and dynamic programming to find the most consistent
tempo, then places beat times accordingly. It's not perfect — tempo
changes within a song will confuse it — but it's the best open-source
option without a GPU.

Confidence: the returned beat times are more reliable than the BPM estimate
on songs with complex rhythms or tempo drift. The BPM is a global average;
don't use it for hard sync on songs that change tempo.
"""

import librosa
import numpy as np


def detect_beats(audio_path: str) -> dict:
    """
    Returns:
        {
          "bpm": float,              # global tempo estimate
          "beats": [float, ...],     # beat timestamps in seconds
          "downbeats": [float, ...], # every 4th beat (estimated bar starts)
        }
    """
    y, sr = librosa.load(audio_path, sr=None, mono=True)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Downbeats: librosa doesn't give us true downbeats without a meter
    # analysis model, so we estimate by taking every 4th beat from the
    # first one. This is wrong on songs in 3/4 or with pickup bars, but
    # it's the correct assumption for the vast majority of popular music.
    downbeats = beat_times[::4]

    return {
        "bpm": round(float(np.squeeze(tempo)), 2),
        "beats": [round(t, 4) for t in beat_times],
        "downbeats": [round(t, 4) for t in downbeats],
    }
