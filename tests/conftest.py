import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AUDIO_DIR = FIXTURES_DIR / "audio"
GROUND_TRUTH_DIR = FIXTURES_DIR / "ground_truth"


@pytest.fixture(scope="session", autouse=True)
def ensure_fixtures():
    """Generate fixtures if they don't exist yet."""
    if not AUDIO_DIR.exists() or not list(AUDIO_DIR.glob("*.wav")):
        from tests.fixtures.generate_fixtures import generate_all

        generate_all()


@pytest.fixture
def audio_dir():
    return AUDIO_DIR


@pytest.fixture
def c_major_scale_path():
    return AUDIO_DIR / "c_major_scale.wav"


@pytest.fixture
def silence_path():
    return AUDIO_DIR / "silence.wav"


@pytest.fixture
def noise_path():
    return AUDIO_DIR / "noise.wav"


@pytest.fixture
def major_triad_path():
    return AUDIO_DIR / "major_triad.wav"


@pytest.fixture
def long_audio_path():
    return AUDIO_DIR / "long_audio.wav"


@pytest.fixture
def ground_truth(request):
    """Load ground truth JSON by filename stem."""
    name = request.param
    path = GROUND_TRUTH_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def tmp_song_dir(tmp_path):
    """Temporary directory mimicking backend/data/<song_id>/."""
    song_dir = tmp_path / "test_song_001"
    (song_dir / "stems").mkdir(parents=True, exist_ok=True)
    (song_dir / "transcription_cache").mkdir(parents=True, exist_ok=True)
    return song_dir
