import numpy as np, soundfile as sf, tempfile
from pathlib import Path
import librosa

sr = 22050
dur = 24.0
t = np.linspace(0, dur, int(sr * dur), endpoint=False)
left = np.sin(2 * np.pi * 220 * t)
middle = np.sin(2 * np.pi * 330 * t)
right = np.sin(2 * np.pi * 440 * t)
y = np.concatenate([
    left[: int(sr * 8)],
    middle[int(sr * 8): int(sr * 16)],
    right[int(sr * 16):],
]).astype(np.float32)
with tempfile.TemporaryDirectory(prefix='mwtn-debug-') as tmpdir:
    p = Path(tmpdir) / 'synthetic.wav'
    sf.write(p, y, sr)
    y2, sr2 = librosa.load(str(p), sr=22050, mono=True, duration=min(dur,600))
    frame_length = max(1024, int(sr2 * 0.5))
    hop_length = frame_length // 4
    energy = np.abs(librosa.stft(y2, n_fft=frame_length, hop_length=hop_length))
    power = np.mean(np.square(energy), axis=0)
    smooth = np.convolve(power, np.ones(min(9, power.size)) / min(9, power.size), mode='same')
    baseline = float(np.median(smooth)) if smooth.size else 0.0
    threshold = max(float(np.max(smooth) * 0.35), baseline + 1e-9)
    print('threshold', threshold)
    if np.any(smooth > threshold):
        change = np.diff(smooth)
        if change.size > 0:
            candidates = np.where(change > max(np.std(change) * 0.5, 1e-6))[0]
            print('cand', candidates, candidates.size)
            if candidates.size > 0:
                boundary_frames = np.unique(np.clip(candidates + 1, 0, smooth.size - 1))
                boundary_times = librosa.frames_to_time(boundary_frames, sr=sr2, hop_length=hop_length)
                edges = [0.0] + [float(t) for t in boundary_times if 0.0 < float(t) < dur] + [float(dur)]
                edges = sorted(set(round(float(v), 3) for v in edges))
                print('edges', edges)
            else:
                edges = [0.0, dur]
        else:
            edges = [0.0, dur]
    else:
        edges = [0.0, dur]
    if len(edges) < 2:
        edges = [0.0, dur]
    if len(edges) == 2:
        sections_count = max(2, min(6, int(dur / 20.0)))
        step = dur / float(sections_count)
        edges = [0.0] + [round(float(i * step), 3) for i in range(1, sections_count)] + [round(float(dur), 3)]
    print('final edges', edges)
    raw = []
    for i in range(len(edges)-1):
        s, e = edges[i], edges[i+1]
        if e - s >= 1.0:
            raw.append({'start': float(s), 'end': float(e), 'label': 'part'})
    print('raw', raw)
