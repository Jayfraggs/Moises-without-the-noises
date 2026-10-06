import json
import re
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from backend.schema.events import AnyMusicalEvent
from backend.schema.manifest import SongManifest
from backend.schema.units import MIDI_PITCH_MAX, MIDI_PITCH_MIN, SUPPORTED_SCHEMA_VERSIONS


def validate_manifest(raw: dict) -> SongManifest:
    try:
        return SongManifest.model_validate(raw)
    except ValidationError as exc:
        errors = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", ()))
            msg = error.get("msg", "Invalid value")
            errors.append({"field": loc or "payload", "message": msg})
        raise HTTPException(status_code=422, detail={"errors": errors}) from exc


def validate_event_list(raw: list[dict]) -> list[AnyMusicalEvent]:
    validated: list[AnyMusicalEvent] = []
    errors: list[dict] = []

    for index, item in enumerate(raw):
        try:
            validated.append(AnyMusicalEvent.model_validate(item))
        except ValidationError as exc:
            for error in exc.errors():
                loc = ".".join(str(part) for part in error.get("loc", ()))
                msg = error.get("msg", "Invalid value")
                errors.append({"index": index, "field": loc or "payload", "message": msg})

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": errors, "valid_count": len(validated), "error_count": len(errors)},
        )

    return validated


def validate_schema_version(data: dict | list) -> str:
    if not isinstance(data, dict):
        return "legacy"

    version = data.get("schema_version")
    if version is None:
        return "legacy"

    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported schema version: {version!r}. Supported: {SUPPORTED_SCHEMA_VERSIONS}",
        )

    return str(version)


def validate_song_id(song_id: str) -> str:
    if not isinstance(song_id, str) or not re.fullmatch(r"^[a-zA-Z0-9_\-]{1,64}$", song_id):
        raise HTTPException(status_code=400, detail=f"Invalid song_id: {song_id!r}")
    return song_id


def validate_note_event_patch(patch: dict) -> dict:
    allowed_keys = {"midi_pitch", "start_time", "end_time", "velocity", "confidence"}
    validated: dict = {}

    for key, value in patch.items():
        if key not in allowed_keys:
            raise HTTPException(status_code=400, detail=f"Unknown patch field: {key!r}")

        if key == "midi_pitch":
            if not isinstance(value, int) or not (MIDI_PITCH_MIN <= value <= MIDI_PITCH_MAX):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid midi_pitch: {value!r}. Must be an int in [{MIDI_PITCH_MIN}, {MIDI_PITCH_MAX}]",
                )
        elif key in {"start_time", "end_time"}:
            if not isinstance(value, (int, float)) or float(value) < 0.0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid {key}: {value!r}. Must be a float >= 0.0",
                )
        elif key == "velocity":
            if not isinstance(value, int) or not (0 <= value <= 127):
                raise HTTPException(status_code=400, detail=f"Invalid velocity: {value!r}. Must be an int in [0, 127]")
        elif key == "confidence":
            if not isinstance(value, (int, float)) or not (0.0 <= float(value) <= 1.0):
                raise HTTPException(status_code=400, detail=f"Invalid confidence: {value!r}. Must be a float in [0.0, 1.0]")

        validated[key] = value

    if "start_time" in validated and "end_time" in validated:
        if float(validated["end_time"]) <= float(validated["start_time"]):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid end_time: {validated['end_time']!r}. Must be greater than start_time {validated['start_time']!r}",
            )

    return validated


def load_json_safe(path: Path) -> dict | list:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {path}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON at {path}: {exc}") from exc
