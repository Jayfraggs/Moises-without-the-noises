"""
vocal_split.py — Second-pass vocal separation: lead vs backing vocals.

Takes an already-isolated vocals.wav (from the first Demucs pass) and
runs a specialised model that is trained specifically to separate
lead/primary vocals from backing/harmony vocals.

Model used: UVR-BVE-4B_SN-44100-1 via audio-separator (karaokenerds/
python-audio-separator, MIT licence).  This model is trained exclusively
for background-vocal extraction and outperforms generic 2-stem models
for this task.

Fallback model: UVR_MDXNET_KARA_2 — also from audio-separator, slightly
lower quality for this specific task but wider availability.

Install (Colab / local):
    pip install "audio-separator[cpu]"
    # For GPU:
    pip install "audio-separator[gpu]"

Data cost: ~200 MB ONNX model downloaded on first use (cached by
audio-separator in ~/.cache/audio-separator/).

Output:
    <song_dir>/lead_vocals.wav    — primary / foreground vocal
    <song_dir>/backing_vocals.wav — harmonies / background vocal

The function writes files and returns a dict with the paths.  It never
raises on a soft failure — it logs and returns {} so the caller can
degrade gracefully.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger("mwtn.vocal_split")

# Preference order: most BVE-specific → generic kara fallback.
_MODEL_PREFERENCE = [
    "UVR-BVE-4B_SN-44100-1",   # best for BVE (background vocal extraction)
    "UVR_MDXNET_KARA_2",        # good general vocal split
]


def run_vocal_split(
    song_dir: Path,
    report=None,
) -> dict[str, Path]:
    """
    Split vocals.wav into lead_vocals.wav + backing_vocals.wav.

    Parameters
    ----------
    song_dir : Path
        The song's data directory; must contain vocals.wav.
    report : callable(str) | None
        Progress callback — same signature as used in separation.py.

    Returns
    -------
    dict mapping stem name → Path, e.g.
        { "lead_vocals": Path(...), "backing_vocals": Path(...) }
    Returns {} on any non-fatal failure.
    """

    def _report(msg: str) -> None:
        if report:
            report(msg)
        logger.info("vocal_split: %s", msg)

    vocals_wav = song_dir / "vocals.wav"
    if not vocals_wav.exists():
        _report("vocals.wav not found — vocal split skipped")
        return {}

    try:
        from audio_separator.separator import Separator
    except ImportError:
        _report(
            "audio-separator not installed — vocal split skipped "
            "(pip install 'audio-separator[cpu]' to enable)"
        )
        return {}

    tmp_out = song_dir / "_vocal_split_raw"
    tmp_out.mkdir(exist_ok=True)

    model_used: str | None = None
    output_files: list[Path] = []

    for model_name in _MODEL_PREFERENCE:
        try:
            _report(f"Loading vocal-split model {model_name}…")
            sep = Separator(
                model_name=model_name,
                output_dir=str(tmp_out),
                output_format="WAV",
            )
            sep.load_model()
            _report("Running vocal split (may take 30–120 s on CPU)…")
            sep.separate(str(vocals_wav))
            output_files = list(tmp_out.glob("*.wav"))
            if output_files:
                model_used = model_name
                break
            _report(f"Model {model_name} produced no output — trying next")
        except Exception as exc:
            _report(f"Model {model_name} failed ({exc}) — trying next")

    if not output_files:
        _report("All vocal-split models failed — skipping")
        shutil.rmtree(tmp_out, ignore_errors=True)
        return {}

    # ── Normalise output filenames ────────────────────────────────────────────
    # audio-separator appends stem descriptors to the filename; we normalise
    # them to lead_vocals.wav and backing_vocals.wav regardless of the model.
    #
    # BVE model: *_(Vocals).wav  and *_(Instrumental).wav  (confusingly named)
    #   The "(Vocals)" output is the LEAD vocal; "(Instrumental)" is BVE.
    # KARA model: *_(Vocals).wav  and *_(Instrumental).wav — same naming.
    stem_files: dict[str, Path] = {}

    for f in output_files:
        stem_lower = f.stem.lower()
        # The primary vocal output contains "(vocals)" in the filename
        if "vocal" in stem_lower and "instrumental" not in stem_lower:
            dest = song_dir / "lead_vocals.wav"
            shutil.copy(f, dest)
            stem_files["lead_vocals"] = dest
        elif "instrumental" in stem_lower or "backing" in stem_lower or "bve" in stem_lower:
            dest = song_dir / "backing_vocals.wav"
            shutil.copy(f, dest)
            stem_files["backing_vocals"] = dest
        # Anything else: skip (shouldn't happen with these models)

    shutil.rmtree(tmp_out, ignore_errors=True)

    if stem_files:
        _report(
            f"Vocal split complete: {list(stem_files)} (model: {model_used})"
        )
    else:
        _report("Vocal split: could not map output filenames — check model output")

    return stem_files
