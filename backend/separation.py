"""
separation.py

Runs Demucs locally on-device. This is the SLOW path -- on a CPU-only
machine (no GPU), expect roughly 3-10x realtime, so a 4-minute song can
take 15-40 minutes. That is expected behavior, not a bug.

If you have access to Google Colab, colab_notebook.ipynb runs the identical
separation + note extraction on a free GPU in well under a minute per song,
then you drop the output folder straight into backend/data/. This local
path exists so the app can also work as a single drop-a-file-in tool
without leaving the desktop, at the cost of speed.
"""

import subprocess
import sys
import shutil
from pathlib import Path

from note_extraction import extract_note_timeline, FREQ_RANGES

DATA_DIR = Path(__file__).parent / "data"
MODEL_NAME = "htdemucs"

# Only these Demucs output stems get note detection attempted. "drums" is
# excluded because pitch tracking on percussion is meaningless. See the
# limitation note in note_extraction.py for why "other" is best-effort.
NOTE_ELIGIBLE_STEMS = list(FREQ_RANGES.keys())


def run_separation(input_audio_path: Path, song_id: str, progress_callback=None):
    """
    Runs Demucs on input_audio_path, then note extraction on the eligible
    stems, and writes everything into backend/data/<song_id>/.

    progress_callback(str) is called with human-readable status strings so
    the caller (main.py's background job) can surface progress via polling.
    Demucs itself doesn't expose fine-grained progress hooks through its
    Python API in a stable way across versions, so the granularity here is
    "which phase we're in," not a percentage. If you need a real progress
    bar, the CLI's stderr output does include a tqdm progress line you could
    parse -- not done here to avoid depending on Demucs' internal log format.
    """

    def report(msg):
        if progress_callback:
            progress_callback(msg)

    song_dir = DATA_DIR / song_id
    song_dir.mkdir(parents=True, exist_ok=True)

    report("Running Demucs separation (this is the slow part on CPU)...")

    # Demucs writes output to <out>/<model_name>/<track_name>/<stem>.wav
    # We call it via subprocess rather than importing demucs' internals
    # directly -- the CLI is the stable, documented interface; the Python
    # internals have changed across Demucs versions.
    demucs_out = song_dir / "_demucs_raw"
    result = subprocess.run(
        [
            sys.executable, "-m", "demucs",
            "-n", MODEL_NAME,
            "-o", str(demucs_out),
            str(input_audio_path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Demucs failed:\n{result.stderr[-2000:]}")

    track_name = input_audio_path.stem
    stems_source_dir = demucs_out / MODEL_NAME / track_name

    if not stems_source_dir.exists():
        raise RuntimeError(
            f"Expected Demucs output at {stems_source_dir} but it doesn't exist. "
            f"Demucs stdout/stderr:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"
        )

    report("Separation complete. Moving stems into place...")

    stem_files = {}
    for wav_file in stems_source_dir.glob("*.wav"):
        stem_name = wav_file.stem  # "vocals", "drums", "bass", "other"
        dest = song_dir / f"{stem_name}.wav"
        shutil.copy(wav_file, dest)
        stem_files[stem_name] = dest

    # Clean up Demucs' intermediate output -- we've copied what we need.
    shutil.rmtree(demucs_out, ignore_errors=True)

    report("Running note detection on eligible stems...")

    notes_written = []
    for stem_name in NOTE_ELIGIBLE_STEMS:
        if stem_name not in stem_files:
            continue
        try:
            timeline = extract_note_timeline(str(stem_files[stem_name]), stem_name)
            import json
            notes_path = song_dir / f"notes_{stem_name}.json"
            notes_path.write_text(json.dumps(timeline))
            notes_written.append(stem_name)
        except Exception as e:
            # Note detection failing shouldn't take down the whole import --
            # the user still gets working stems for practice, just without
            # the note overlay on that one stem.
            report(f"Note detection failed for {stem_name}: {e}")

    report("Writing manifest...")

    import json
    manifest = {
        "song_id": song_id,
        "stems": list(stem_files.keys()),
        "notes_available": notes_written,
    }
    (song_dir / "manifest.json").write_text(json.dumps(manifest))

    report("Done.")
    return manifest
