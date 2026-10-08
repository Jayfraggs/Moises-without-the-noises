"""
separation.py — multi-engine audio source separation for mwtn.

This is the LOCAL (slow) path. On a CPU-only machine, all engines are
significantly slower than on GPU. Use the Colab notebook for fast processing.

═══════════════════════════════════════════════════════════════════════════════
ENGINES
═══════════════════════════════════════════════════════════════════════════════

DEMUCS FAMILY  (Facebook Research / Meta AI — MIT licence)
  htdemucs_ft   4-stem fine-tuned model (vocals, drums, bass, other).
                Fastest Demucs option. Very high quality. Best default
                when you don't need guitar/piano as separate tracks.
                pip: demucs (already in requirements.txt)

  htdemucs_6s   6-stem model (adds guitar + piano). ~10-20 % slower than
                htdemucs_ft. May have slight bleed between guitar/piano.
                Best for multi-instrument practice.
                pip: demucs (already in requirements.txt)

SPLEETER  (Deezer Research — MIT licence)
  spleeter:2stems  vocals / accompaniment.  Fastest of all engines on GPU
                   (100× realtime claimed by Deezer). Lowest quality on
                   modern benchmarks.  Good when you ONLY want karaoke.
                   pip: spleeter  (pulls TensorFlow ~500 MB)

  spleeter:4stems  vocals / drums / bass / other.
                   pip: spleeter

  spleeter:5stems  vocals / drums / bass / piano / other.
                   pip: spleeter

OPEN-UNMIX  (Inria — MIT licence)
  umxl          4-stem LSTM model (vocals, drums, bass, other) trained on
                extra private data.  Good quality, stable pip story, best
                for research reproducibility / comparison.
                pip: openunmix torchaudio

  umxhq         Same architecture, trained on MUSDB18-HQ only.  Slightly
                lower quality than umxl but fully reproducible from public
                data.
                pip: openunmix torchaudio

MDX-NET  (Kimberley Jensen / Anjok07 — MIT licence via audio-separator)
  mdx-vocalft   MDX-Net UVR_MDXNET_KARA_2 — cleaner vocal isolation than
                Demucs on some material (notably less bleed on reverbed
                vocals).  2-stem only (vocals + instrumental).
                pip: audio-separator[cpu]

  mdx-inst-hq3  MDX-Net UVR-MDX-NET-Inst_HQ_3 — high-quality instrumental
                extraction.  2-stem.
                pip: audio-separator[cpu]

BS-RoFORMER  (Lu et al. 2024 — MIT licence via bs-roformer-infer)
  bs-roformer   State-of-the-art 6-stem separation (vocals, drums, bass,
                guitar, piano, other).  Best overall quality on current
                benchmarks.  Requires model download on first use (~400 MB).
                pip: bs-roformer-infer

MEL-BAND RoFORMER  (Lu et al. 2024 — MIT licence via melband-roformer-infer)
  melband-roformer  Best-in-class VOCAL isolation specifically.  Outputs
                    vocals + instrumental (2 stems).  Smaller model than
                    BS-RoFormer, faster on CPU.
                    pip: melband-roformer-infer

INSTALL NOTES
─────────────
All engines are optional — only the Demucs engines are installed by default
(they are in requirements.txt).  The other engines are installed on-demand
when the user selects them.  If a required package is missing at runtime,
run_separation() raises a clear RuntimeError pointing at the right pip
command.

DATA COST (first run, Colab session)
─────────────────────────────────────
• demucs htdemucs_ft / htdemucs_6s : ~2.0–2.3 GB
• spleeter any variant              : ~0.5 GB models + 0.5 GB TF
• openunmix umxl / umxhq            : ~0.4 GB
• audio-separator mdx-*             : ~0.3 GB per ONNX model
• bs-roformer-infer                 : ~0.4 GB checkpoint
• melband-roformer-infer            : ~0.3 GB checkpoint
"""

import shutil
import subprocess
import sys
from pathlib import Path

from note_extraction import extract_note_timeline, FREQ_RANGES

DATA_DIR = Path(__file__).parent / "data"

# ─── Model registry ───────────────────────────────────────────────────────────
# Each entry:
#   stems        : list of WAV stems the engine writes (used to build manifest)
#   description  : shown in the UI model-selector dropdown
#   engine       : internal routing key (maps to _run_<engine>())
#   engine_key   : argument forwarded to the engine runner
#   pip_hint     : human-readable install hint shown on ImportError
#   data_cost_mb : approximate first-run download in MB (shown in UI warning)

SUPPORTED_MODELS: dict[str, dict] = {
    # ── Demucs ───────────────────────────────────────────────────────────────
    "htdemucs_ft": {
        "stems": ["vocals", "drums", "bass", "other"],
        "description": "Demucs 4-stem fine-tuned — fast, very clean (recommended default)",
        "engine": "demucs",
        "engine_key": "htdemucs_ft",
        "pip_hint": "pip install demucs",
        "data_cost_mb": 2000,
    },
    "htdemucs_6s": {
        "stems": ["vocals", "drums", "bass", "other", "guitar", "piano"],
        "description": "Demucs 6-stem — adds guitar + piano, ~15 % slower",
        "engine": "demucs",
        "engine_key": "htdemucs_6s",
        "pip_hint": "pip install demucs",
        "data_cost_mb": 2300,
    },
    # ── Spleeter ─────────────────────────────────────────────────────────────
    "spleeter:2stems": {
        "stems": ["vocals", "accompaniment"],
        "description": "Spleeter 2-stem — fastest, karaoke only (vocals + accompaniment)",
        "engine": "spleeter",
        "engine_key": "spleeter:2stems",
        "pip_hint": "pip install spleeter",
        "data_cost_mb": 1000,
    },
    "spleeter:4stems": {
        "stems": ["vocals", "drums", "bass", "other"],
        "description": "Spleeter 4-stem — vocals/drums/bass/other, fast on GPU",
        "engine": "spleeter",
        "engine_key": "spleeter:4stems",
        "pip_hint": "pip install spleeter",
        "data_cost_mb": 1100,
    },
    "spleeter:5stems": {
        "stems": ["vocals", "drums", "bass", "piano", "other"],
        "description": "Spleeter 5-stem — adds piano to the 4-stem split",
        "engine": "spleeter",
        "engine_key": "spleeter:5stems",
        "pip_hint": "pip install spleeter",
        "data_cost_mb": 1200,
    },
    # ── Open-Unmix ────────────────────────────────────────────────────────────
    "umxl": {
        "stems": ["vocals", "drums", "bass", "other"],
        "description": "Open-Unmix umxl — 4-stem LSTM, trained on extra data, stable",
        "engine": "openunmix",
        "engine_key": "umxl",
        "pip_hint": "pip install openunmix torchaudio",
        "data_cost_mb": 400,
    },
    "umxhq": {
        "stems": ["vocals", "drums", "bass", "other"],
        "description": "Open-Unmix umxhq — 4-stem LSTM, MUSDB18-HQ baseline (research)",
        "engine": "openunmix",
        "engine_key": "umxhq",
        "pip_hint": "pip install openunmix torchaudio",
        "data_cost_mb": 400,
    },
    # ── MDX-Net ──────────────────────────────────────────────────────────────
    "mdx-vocalft": {
        "stems": ["vocals", "instrumental"],
        "description": "MDX-Net Vocal FT — 2-stem, clean vocal isolation, good on reverb",
        "engine": "mdxnet",
        "engine_key": "UVR_MDXNET_KARA_2",
        "pip_hint": "pip install 'audio-separator[cpu]'",
        "data_cost_mb": 350,
    },
    "mdx-inst-hq3": {
        "stems": ["vocals", "instrumental"],
        "description": "MDX-Net Inst HQ3 — 2-stem, high-quality instrumental extraction",
        "engine": "mdxnet",
        "engine_key": "UVR-MDX-NET-Inst_HQ_3",
        "pip_hint": "pip install 'audio-separator[cpu]'",
        "data_cost_mb": 350,
    },
    # ── BS-RoFormer ──────────────────────────────────────────────────────────
    "bs-roformer": {
        "stems": ["vocals", "drums", "bass", "guitar", "piano", "other"],
        "description": "BS-RoFormer 6-stem — state-of-the-art quality, best overall benchmark",
        "engine": "bs_roformer",
        "engine_key": "default",
        "pip_hint": "pip install bs-roformer-infer",
        "data_cost_mb": 400,
    },
    # ── Mel-Band RoFormer ────────────────────────────────────────────────────
    "melband-roformer": {
        "stems": ["vocals", "instrumental"],
        "description": "Mel-Band RoFormer — best-in-class vocal isolation, 2-stem, fast",
        "engine": "melband_roformer",
        "engine_key": "default",
        "pip_hint": "pip install melband-roformer-infer",
        "data_cost_mb": 300,
    },
}

DEFAULT_MODEL = "htdemucs_6s"

# Stems eligible for note detection (pitch makes sense, drums do not)
NOTE_ELIGIBLE_STEMS = list(FREQ_RANGES.keys())

# Compatibility helper used by tests and ingestion routines.
STEM_NAME_ALIASES: dict[str, str] = {
    "vocal": "vocals",
    "vox": "vocals",
    "lead_vocals": "vocals",
    "lead_vocal": "vocals",
    "voice": "vocals",
    "singer": "vocals",
    "drum": "drums",
    "beat": "drums",
    "percussion": "drums",
    "perc": "drums",
    "kick": "drums",
    "bass_guitar": "bass",
    "bass_line": "bass",
    "gtr": "guitar",
    "guitars": "guitar",
    "electric_guitar": "guitar",
    "acoustic_guitar": "guitar",
    "rhythm_guitar": "guitar",
    "piano": "piano",
    "keys": "piano",
    "keyboard": "piano",
    "keyboards": "piano",
    "synth": "piano",
    "accompaniment": "instrumental",
    "backing": "instrumental",
    "backing_track": "instrumental",
    "music": "instrumental",
    "inst": "instrumental",
    "no_vocals": "instrumental",
}


def _normalise_stem_name(raw: str) -> str:
    """Return a canonical stem name for compatibility with the ingestion contract."""
    key = raw.lower().strip().replace(" ", "_").replace("-", "_")
    return STEM_NAME_ALIASES.get(key, key)


# ─── Engine runners ───────────────────────────────────────────────────────────

def _run_demucs(input_path: Path, song_dir: Path, engine_key: str, report) -> dict[str, Path]:
    """Run Demucs via subprocess (stable public CLI)."""
    report(f"Running Demucs ({engine_key}) — slow on CPU, fast on GPU…")
    demucs_out = song_dir / "_demucs_raw"
    result = subprocess.run(
        [sys.executable, "-m", "demucs", "-n", engine_key, "-o", str(demucs_out), str(input_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Demucs failed:\n{result.stderr[-2000:]}")

    stems_source = demucs_out / engine_key / input_path.stem
    if not stems_source.exists():
        raise RuntimeError(f"Expected Demucs output at {stems_source} — not found.")

    stem_files = {}
    for wav in stems_source.glob("*.wav"):
        dest = song_dir / wav.name
        shutil.copy(wav, dest)
        stem_files[wav.stem] = dest

    shutil.rmtree(demucs_out, ignore_errors=True)
    return stem_files


def _run_spleeter(input_path: Path, song_dir: Path, engine_key: str, report) -> dict[str, Path]:
    """
    Run Spleeter via its CLI subprocess.
    Spleeter writes <output_dir>/<track_stem>/<stem>.wav.
    We copy those WAVs flat into song_dir.
    """
    try:
        import spleeter  # noqa: F401 — just check it's installed
    except ImportError:
        raise RuntimeError(
            "Spleeter is not installed.\n"
            "Run: pip install spleeter\n"
            "Note: Spleeter requires TensorFlow (~500 MB download on first run)."
        )

    report(f"Running Spleeter ({engine_key})…")
    spleeter_out = song_dir / "_spleeter_raw"

    result = subprocess.run(
        [
            sys.executable, "-m", "spleeter", "separate",
            "-p", engine_key,
            "-o", str(spleeter_out),
            str(input_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Spleeter failed:\n{result.stderr[-2000:]}")

    # Spleeter writes: <out>/<input_stem>/<stem>.wav
    track_subdir = spleeter_out / input_path.stem
    if not track_subdir.exists():
        raise RuntimeError(f"Expected Spleeter output at {track_subdir} — not found.")

    stem_files = {}
    for wav in track_subdir.glob("*.wav"):
        dest = song_dir / wav.name
        shutil.copy(wav, dest)
        stem_files[wav.stem] = dest

    shutil.rmtree(spleeter_out, ignore_errors=True)
    return stem_files


def _run_openunmix(input_path: Path, song_dir: Path, engine_key: str, report) -> dict[str, Path]:
    """
    Run Open-Unmix via its Python API.
    openunmix separates into vocals/drums/bass/other and writes WAV files.
    """
    try:
        import openunmix  # noqa: F401
        import torch
        import torchaudio
        import soundfile as sf
        import numpy as np
    except ImportError as e:
        raise RuntimeError(
            f"Open-Unmix dependency missing: {e}\n"
            "Run: pip install openunmix torchaudio"
        )

    report(f"Loading Open-Unmix model ({engine_key})…")
    separator = torch.hub.load(
        "sigsep/open-unmix-pytorch",
        engine_key,
        trust_repo=True,
    )
    separator.eval()

    report("Loading audio…")
    audio, sr = torchaudio.load(str(input_path))
    if audio.shape[0] == 1:
        audio = audio.repeat(2, 1)  # mono → stereo
    audio = audio.unsqueeze(0)  # (1, channels, samples)

    if sr != separator.sample_rate:
        resamp = torchaudio.transforms.Resample(sr, separator.sample_rate)
        audio = resamp(audio)

    report("Separating with Open-Unmix (this is the slow step)…")
    with torch.no_grad():
        estimates = separator(audio)
    # estimates: (1, num_targets, channels, samples)

    targets = ["vocals", "drums", "bass", "other"]
    stem_files = {}
    for i, name in enumerate(targets):
        wav = estimates[0, i].cpu().numpy().T  # (samples, channels)
        dest = song_dir / f"{name}.wav"
        sf.write(str(dest), wav, separator.sample_rate)
        stem_files[name] = dest

    return stem_files


def _run_mdxnet(input_path: Path, song_dir: Path, engine_key: str, report) -> dict[str, Path]:
    """
    Run MDX-Net via the audio-separator package (karaokenerds/python-audio-separator).
    Outputs 2 stems: primary (instrumental) and secondary (vocals), named by the model.
    We normalise the output filenames to vocals.wav / instrumental.wav.
    """
    try:
        from audio_separator.separator import Separator
    except ImportError:
        raise RuntimeError(
            "audio-separator is not installed.\n"
            "Run: pip install 'audio-separator[cpu]'\n"
            "For GPU acceleration: pip install 'audio-separator[gpu]'"
        )

    report(f"Running MDX-Net ({engine_key})…")
    tmp_out = song_dir / "_mdx_raw"
    tmp_out.mkdir(exist_ok=True)

    separator = Separator(
        model_name=engine_key,
        output_dir=str(tmp_out),
        output_format="WAV",
    )
    separator.load_model()
    output_files = separator.separate(str(input_path))

    stem_files = {}
    # audio-separator appends _(Vocals).wav / _(Instrumental).wav
    for f in tmp_out.glob("*.wav"):
        name_lower = f.stem.lower()
        if "vocals" in name_lower or "vocal" in name_lower:
            dest = song_dir / "vocals.wav"
        elif "instrumental" in name_lower or "accompaniment" in name_lower:
            dest = song_dir / "instrumental.wav"
        else:
            dest = song_dir / f.name
        shutil.copy(f, dest)
        stem_files[dest.stem] = dest

    shutil.rmtree(tmp_out, ignore_errors=True)
    return stem_files


def _run_bs_roformer(input_path: Path, song_dir: Path, engine_key: str, report) -> dict[str, Path]:
    """
    Run BS-RoFormer via bs-roformer-infer (openmirlab/bs-roformer-infer).
    Downloads the default checkpoint on first use (~400 MB, sha256-verified).
    Produces 6 stems: vocals, drums, bass, guitar, piano, other.
    """
    try:
        from bs_roformer import BSRoformerSession
    except ImportError:
        raise RuntimeError(
            "bs-roformer-infer is not installed.\n"
            "Run: pip install bs-roformer-infer\n"
            "First run downloads ~400 MB of model weights."
        )

    report("Loading BS-RoFormer (downloads ~400 MB checkpoint on first run)…")
    tmp_out = song_dir / "_bsroformer_raw"
    tmp_out.mkdir(exist_ok=True)

    # BSRoformerSession auto-downloads the default model on first use.
    with BSRoformerSession() as session:
        report("Separating with BS-RoFormer (slow on CPU)…")
        session.infer(str(input_path.parent), store_dir=str(tmp_out))

    # Collect output WAVs (named <track>_<stem>.wav by the infer package)
    stem_files = {}
    expected = ["vocals", "drums", "bass", "guitar", "piano", "other", "instrumental"]
    for wav in tmp_out.glob("*.wav"):
        for stem_name in expected:
            if f"_{stem_name}." in wav.name.lower() or wav.stem.lower() == stem_name:
                dest = song_dir / f"{stem_name}.wav"
                shutil.copy(wav, dest)
                stem_files[stem_name] = dest
                break

    if not stem_files:
        # Fallback: copy everything as-is
        for wav in tmp_out.glob("*.wav"):
            dest = song_dir / wav.name
            shutil.copy(wav, dest)
            stem_files[wav.stem] = dest

    shutil.rmtree(tmp_out, ignore_errors=True)
    return stem_files


def _run_melband_roformer(input_path: Path, song_dir: Path, engine_key: str, report) -> dict[str, Path]:
    """
    Run Mel-Band RoFormer via melband-roformer-infer (openmirlab/melband-roformer-infer).
    Downloads the Kim vocals checkpoint on first use (~300 MB, sha256-verified).
    Produces 2 stems: vocals + instrumental.
    """
    try:
        from mel_band_roformer import MelBandRoformerSession
    except ImportError:
        raise RuntimeError(
            "melband-roformer-infer is not installed.\n"
            "Run: pip install melband-roformer-infer\n"
            "First run downloads ~300 MB of model weights."
        )

    report("Loading Mel-Band RoFormer (downloads ~300 MB checkpoint on first run)…")
    tmp_out = song_dir / "_melband_raw"
    tmp_out.mkdir(exist_ok=True)

    with MelBandRoformerSession() as session:
        report("Separating with Mel-Band RoFormer…")
        session.infer(str(input_path.parent), store_dir=str(tmp_out))

    stem_files = {}
    for wav in tmp_out.glob("*.wav"):
        name_lower = wav.stem.lower()
        if "vocal" in name_lower:
            dest = song_dir / "vocals.wav"
        elif "instrumental" in name_lower or "accompaniment" in name_lower:
            dest = song_dir / "instrumental.wav"
        else:
            dest = song_dir / wav.name
        shutil.copy(wav, dest)
        stem_files[dest.stem] = dest

    shutil.rmtree(tmp_out, ignore_errors=True)
    return stem_files


# ─── Engine dispatch table ────────────────────────────────────────────────────

_ENGINE_RUNNERS = {
    "demucs":           _run_demucs,
    "spleeter":         _run_spleeter,
    "openunmix":        _run_openunmix,
    "mdxnet":           _run_mdxnet,
    "bs_roformer":      _run_bs_roformer,
    "melband_roformer": _run_melband_roformer,
}


# ─── Public entry point ───────────────────────────────────────────────────────

def run_separation(
    input_audio_path: Path,
    song_id: str,
    model_name: str = DEFAULT_MODEL,
    progress_callback=None,
):
    """
    Runs the selected model on input_audio_path, writes stems + note data
    into backend/data/<song_id>/, and returns the manifest dict.

    progress_callback(str) is called with human-readable progress strings
    that the background job surfaces via the polling API.
    """
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unknown model '{model_name}'.\n"
            f"Supported: {list(SUPPORTED_MODELS.keys())}"
        )

    cfg = SUPPORTED_MODELS[model_name]

    def report(msg: str):
        if progress_callback:
            progress_callback(msg)

    song_dir = DATA_DIR / song_id
    song_dir.mkdir(parents=True, exist_ok=True)

    # ── Run separation engine ──────────────────────────────────────────────
    engine = cfg["engine"]
    runner = _ENGINE_RUNNERS.get(engine)
    if runner is None:
        raise RuntimeError(f"No runner implemented for engine '{engine}'")

    stem_files = runner(input_audio_path, song_dir, cfg["engine_key"], report)

    if not stem_files:
        raise RuntimeError(
            f"Separation produced no output WAV files in {song_dir}. "
            "Check the engine output above for errors."
        )

    # ── Note detection (only on pitch-capable stems) ───────────────────────
    report("Running note detection on eligible stems…")
    notes_written = []
    for stem_name in NOTE_ELIGIBLE_STEMS:
        if stem_name not in stem_files:
            continue
        try:
            import json
            timeline = extract_note_timeline(str(stem_files[stem_name]), stem_name)
            notes_path = song_dir / f"notes_{stem_name}.json"
            notes_path.write_text(json.dumps(timeline))
            notes_written.append(stem_name)
        except Exception as e:
            report(f"Note detection failed for {stem_name} (non-fatal): {e}")

    # ── Stem presence (normalised RMS per stem) ────────────────────────────
    stem_presence: dict[str, float] = {}
    try:
        import soundfile as sf
        import numpy as np
        rms_values = {}
        for stem_name, stem_path in stem_files.items():
            data, _ = sf.read(str(stem_path))
            rms_values[stem_name] = float(np.sqrt(np.mean(data ** 2)))
        max_rms = max(rms_values.values()) if rms_values else 1.0
        stem_presence = {k: round(v / max_rms * 100, 1) for k, v in rms_values.items()}
    except Exception:
        pass

    # ── Write manifest ─────────────────────────────────────────────────────
    report("Writing manifest…")
    import json
    manifest = {
        "song_id": song_id,
        "stems": list(stem_files.keys()),
        "notes_available": notes_written,
        "demucs_model": model_name,   # legacy key — kept for compatibility
        "separation_model": model_name,
        "separation_engine": engine,
        "stem_presence": stem_presence,
    }
    (song_dir / "manifest.json").write_text(json.dumps(manifest))

    report("Done.")
    return manifest
