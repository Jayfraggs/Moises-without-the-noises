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
    yy, srr = librosa.load(str(p), sr=22050, mono=True, duration=min(dur,600))
    print('yy', yy.shape, yy.dtype)
    frame_length = max(1024, int(srr * 0.5))
    hop_length = frame_length // 4
    print('frame', frame_length, 'hop', hop_length)
    E = np.abs(librosa.stft(yy, n_fft=frame_length, hop_length=hop_length))
    power = np.mean(np.square(E), axis=0)
    print('E', E.shape, 'power', power.shape)
    print('power[:10]', power[:10])
    smooth = np.convolve(power, np.ones(min(9, power.size)) / min(9, power.size), mode='same')
    print('smooth min max', smooth.min(), smooth.max())
    baseline = float(np.median(smooth))
    threshold = max(float(np.max(smooth) * 0.35), baseline + 1e-9)
    print('threshold', threshold)
    print('count > threshold', np.count_nonzero(smooth > threshold))
    change = np.diff(smooth)
    print('change std', np.std(change), 'max', np.max(change), 'min', np.min(change))
    if change.size > 0:
        candidates = np.where(change > max(np.std(change) * 0.5, 1e-6))[0]
        print('candidates', candidates[:20], candidates.size)
