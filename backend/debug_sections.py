import numpy as np, soundfile as sf, tempfile
from pathlib import Path
from audio.section_detection import _detect_with_librosa

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
    out = _detect_with_librosa(p, dur)
    print('OUT', out)
