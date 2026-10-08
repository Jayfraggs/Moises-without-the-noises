"""Unit tests for the dependency-free Colab solfège artifact writer."""

import ast
import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def load_write_solfa_files():
    """Load only the pure Colab helper without importing audio dependencies."""
    module_path = Path("colab/mwtn_pipeline.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "write_solfa_files"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"Path": Path, "json": json}
    exec(compile(module, str(module_path), "exec"), namespace)
    return namespace["write_solfa_files"]


def test_write_solfa_files_creates_payload_and_skips_missing_stems(tmp_path: Path) -> None:
    write_solfa_files = load_write_solfa_files()
    (tmp_path / "key.json").write_text(json.dumps({"root": "C", "mode": "major"}), encoding="utf-8")
    (tmp_path / "notes_bass.json").write_text(
        json.dumps([{"start": 0.5, "end": 0.75, "midi": 64}]),
        encoding="utf-8",
    )

    assert write_solfa_files(tmp_path, "test_song") == ["bass"]

    payload = json.loads((tmp_path / "solfa_bass.json").read_text(encoding="utf-8"))
    assert payload["tonic_midi"] == 60
    assert payload["mode"] == "major"
    assert payload["events"] == [{
        "onset_s": 0.5,
        "duration_s": 0.25,
        "pitch_midi": 64,
        "pitch_hz": None,
        "solfa": "Mi",
        "confidence": 1.0,
    }]


def test_write_solfa_files_is_idempotent_and_supports_la_based_minor(tmp_path: Path) -> None:
    write_solfa_files = load_write_solfa_files()
    (tmp_path / "key.json").write_text(json.dumps({"root": "A", "mode": "minor"}), encoding="utf-8")
    (tmp_path / "notes_vocals.json").write_text(
        json.dumps([{"start": 0.0, "end": 0.5, "midi": 69}]),
        encoding="utf-8",
    )

    write_solfa_files(tmp_path, "minor_song")
    write_solfa_files(tmp_path, "minor_song")

    payload = json.loads((tmp_path / "solfa_vocals.json").read_text(encoding="utf-8"))
    assert payload["events"][0]["solfa"] == "La"
