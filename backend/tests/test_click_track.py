import json

import numpy as np
from scipy.io import wavfile

from audio.click_track import generate_click_track


def test_generate_click_track_writes_typed_mono_wav(tmp_path):
    beats_path = tmp_path / "beats.json"
    output_path = tmp_path / "click.wav"
    beats_path.write_text(
        json.dumps({"beats": [{"time_s": 0.0, "beat_number": 1}, {"time_s": 1.0, "beat_number": 2}]}),
        encoding="utf-8",
    )

    result = generate_click_track(beats_path, output_path, sample_rate=10000)

    sample_rate, audio = wavfile.read(result)
    assert result == output_path
    assert sample_rate == 10000
    assert audio.dtype == np.int16
    assert audio.ndim == 1
    assert len(audio) == 30000
    assert np.max(np.abs(audio[1:200])) > 0
    assert np.max(np.abs(audio[10001:10200])) > 0
