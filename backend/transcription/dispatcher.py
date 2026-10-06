from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from backend.schema.events import AnyMusicalEvent
from backend.transcription.config import TranscriptionConfig
from backend.transcription.preprocessing import (
    chunk_audio,
    cleanup_temp_files,
    merge_chunked_events,
    preprocess_for_transcription,
)

PROFILE_MATRIX: dict[str, dict[str, str]] = {
    "vocals": {"fast": "pyin", "standard": "basic_pitch", "high_quality": "basic_pitch"},
    "bass": {"fast": "pyin", "standard": "basic_pitch", "high_quality": "basic_pitch"},
    "piano": {"fast": "basic_pitch", "standard": "basic_pitch", "high_quality": "piano_kong"},
    "guitar": {"fast": "basic_pitch", "standard": "basic_pitch", "high_quality": "basic_pitch"},
    "drums": {"fast": "adtlib", "standard": "adtlib", "high_quality": "adtlib"},
    "other": {"fast": "basic_pitch", "standard": "basic_pitch", "high_quality": "basic_pitch"},
}

GUITAR_QUALITY_CAVEAT = (
    "Guitar transcription quality is lower than vocals or piano with all current open-source models. "
    "Expect errors requiring human review in the Score workspace."
)

FALLBACK_CHAIN: dict[str, list[str]] = {
    "piano_kong": ["basic_pitch"],
    "adtlib": ["basic_pitch"],
    "basic_pitch": ["pyin"],
    "pyin": [],
}

_JOB_STATE: dict[str, dict[str, Any]] = {}


def _load_engine(engine_name: str):
    """Load an engine by name. Returns None if unavailable."""
    from backend.transcription.config import is_engine_available

    if not is_engine_available(engine_name):
        return None

    try:
        if engine_name == "pyin":
            from backend.transcription.engines.pyin import PYINEngine
            return PYINEngine()
        if engine_name == "basic_pitch":
            from backend.transcription.engines.basic_pitch import BasicPitchEngine
            return BasicPitchEngine()
        if engine_name == "piano_kong":
            from backend.transcription.engines.piano_kong import PianoKongEngine
            return PianoKongEngine()
        if engine_name == "adtlib":
            from backend.transcription.engines.drums import ADTLibEngine
            return ADTLibEngine()
    except (ImportError, RuntimeError, AttributeError):
        return None
    return None


def _set_job_state(run_id: str, *, status: str, stage: str, stem: str, song_id: str, warnings: list[str] | None = None, error: str | None = None) -> dict[str, Any]:
    state = {
        "status": status,
        "stage": stage,
        "stem": stem,
        "song_id": song_id,
        "warnings": list(warnings or []),
        "error": error,
    }
    _JOB_STATE[run_id] = state
    return state


def transcribe_stem(
    audio_path: str | Path,
    song_id: str,
    stem_type: str,
    config: TranscriptionConfig,
    cache_dir: Path,
    run_id: str | None = None,
) -> tuple[list, dict]:
    """
    Transcribe one stem. Returns (events, job_info).
    job_info: { "run_id", "engine_used", "cached", "warnings", "status" }
    """
    run_id = run_id or uuid.uuid4().hex
    warnings: list[str] = []
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    _set_job_state(run_id, status="preprocessing", stage="preprocessing", stem=stem_type, song_id=song_id, warnings=warnings)

    preferred_engine_name = PROFILE_MATRIX.get(stem_type, {}).get(config.quality_profile, "basic_pitch")
    audio_file = Path(audio_path)

    try:
        audio_bytes = audio_file.read_bytes()
    except FileNotFoundError as exc:
        _set_job_state(run_id, status="failed", stage="preprocessing", stem=stem_type, song_id=song_id, warnings=warnings, error=str(exc))
        raise FileNotFoundError(f"Audio file not found: {audio_file}") from exc

    cache_key = hashlib.sha256(
        audio_bytes + preferred_engine_name.encode() + config.config_hash.encode()
    ).hexdigest()[:16]
    cache_path = cache_dir / f"{stem_type}_{cache_key}.json"

    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        adapter = TypeAdapter(AnyMusicalEvent)
        events = [adapter.validate_python(item) for item in payload]
        _set_job_state(run_id, status="complete", stage="complete", stem=stem_type, song_id=song_id, warnings=warnings, error=None)
        return events, {"run_id": run_id, "engine_used": preferred_engine_name, "cached": True, "warnings": warnings, "status": "complete"}

    engine_name = preferred_engine_name
    engine = _load_engine(engine_name)
    fallback_used = False
    if engine is None:
        for candidate in FALLBACK_CHAIN.get(engine_name, []):
            engine = _load_engine(candidate)
            if engine is not None:
                engine_name = candidate
                fallback_used = True
                break
        if engine is None:
            _set_job_state(run_id, status="failed", stage="failed", stem=stem_type, song_id=song_id, warnings=warnings, error=f"No transcription engine available for stem={stem_type}")
            raise RuntimeError(f"No transcription engine available for stem={stem_type}")

    if stem_type == "guitar":
        warnings.append(GUITAR_QUALITY_CAVEAT)
    if fallback_used:
        warnings.append(f"Preferred engine unavailable; used {engine_name} instead")

    engine_info = engine.model_info() if hasattr(engine, "model_info") else {}
    config.source_model = f"{engine_info.get('engine', engine_name)}_{engine_info.get('version', 'unknown')}"

    _set_job_state(run_id, status="preprocessing", stage="preprocessing", stem=stem_type, song_id=song_id, warnings=warnings, error=None)

    temp_paths: list[Path] = []
    try:
        preproc_path = preprocess_for_transcription(audio_file, config)
        temp_paths.append(Path(preproc_path))

        chunks = chunk_audio(preproc_path, config.chunk_duration_s, config.chunk_overlap_s, config.sample_rate)
        chunk_files = [Path(chunk_path) for chunk_path, _ in chunks]
        temp_paths.extend(chunk_files)

        _set_job_state(run_id, status="transcribing", stage="transcribing", stem=stem_type, song_id=song_id, warnings=warnings, error=None)

        chunk_results: list[tuple[list, float]] = []
        for idx, (chunk_path, offset) in enumerate(chunks):
            try:
                events_for_chunk = engine.transcribe(str(chunk_path), config)
                chunk_results.append((events_for_chunk, offset))
            except Exception as exc:  # pragma: no cover - depends on engine runtime behavior
                warnings.append(f"Chunk {idx} failed for stem={stem_type}: {exc}")
                _set_job_state(run_id, status="transcribing", stage="transcribing", stem=stem_type, song_id=song_id, warnings=warnings, error=str(exc))

        _set_job_state(run_id, status="merging", stage="merging", stem=stem_type, song_id=song_id, warnings=warnings, error=None)
        merged_events = merge_chunked_events(chunk_results)

        if not merged_events:
            events = []
        else:
            adapter = TypeAdapter(AnyMusicalEvent)
            validated_events: list[Any] = []
            for event in merged_events:
                validated_events.append(adapter.validate_python(event.model_dump(mode="json")))
            events = validated_events

        _set_job_state(run_id, status="validating", stage="validating", stem=stem_type, song_id=song_id, warnings=warnings, error=None)

        cache_payload = json.dumps([event.model_dump(mode="json") for event in events])
        with open(cache_path, "w", encoding="utf-8") as handle:
            handle.write(cache_payload)

        _set_job_state(run_id, status="complete", stage="complete", stem=stem_type, song_id=song_id, warnings=warnings, error=None)

        job_info = {
            "run_id": run_id,
            "engine_used": engine_name,
            "cached": False,
            "warnings": warnings,
            "status": "complete",
        }
        return events, job_info
    finally:
        cleanup_temp_files(temp_paths)


def get_job_status(run_id: str) -> dict:
    return _JOB_STATE.get(run_id, {"status": "not_found"})
