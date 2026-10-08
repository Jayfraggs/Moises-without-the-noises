from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schema.units import SCHEMA_VERSION


class SeparationEngineInfo(BaseModel):
    name: str  # Separation engine family name such as demucs.
    model: str  # Model identifier such as htdemucs_6s.
    version: str | None = None  # Engine version string when available.
    profile: str = "standard"  # Separation profile name for tuning or deployment context.


class TranscriptionRun(BaseModel):
    run_id: str  # UUID for the transcription run.
    stem: str  # Stem name processed by this run.
    engine: str  # Transcription engine name.
    engine_version: str | None = None  # Engine version string.
    config_hash: str | None = None  # Hash of configuration used by the run.
    completed_at: str | None = None  # ISO8601 timestamp for completion.
    status: str = "complete"  # Run status: complete, failed, or partial.
    error: str | None = None  # Failure details when the run did not complete successfully.


class ArtifactEntry(BaseModel):
    artifact_id: str  # Stable identifier for the artifact registry entry.
    artifact_type: str  # Artifact type such as musicxml, midi, events_json, or beats.
    file_path: str  # Relative path from the song directory to the artifact file.
    source_run_id: str | None = None  # Run ID that produced this artifact.
    schema_version: str  # Schema version used by the artifact payload.
    model: str | None = None  # Upstream model or exporter used to create the artifact.
    config_hash: str | None = None  # Configuration hash associated with artifact generation.
    created_at: str | None = None  # ISO8601 timestamp for artifact creation.
    is_stale: bool = False  # Whether the artifact should be regenerated before use.


class SongManifest(BaseModel):
    song_id: str  # Unique song identifier derived from the source file or folder name.
    title: str | None = None  # Display title of the song.
    stems: list[str] = Field(default_factory=list)  # Canonical stem list for this song.
    notes_available: list[str] = Field(default_factory=list)  # Stem names with note extraction artifacts.
    has_lyrics: bool = False  # Whether lyrics JSON is available.
    has_beats: bool = False  # Whether beat metadata is available.
    has_key: bool = False  # Whether key metadata is available.
    bpm: float | None = None  # Song tempo in beats per minute when known.
    key: str | None = None  # Legacy key string retained for UI compatibility.
    schema_version: str = Field(default_factory=lambda: SCHEMA_VERSION)  # Current manifest schema version.
    source_hash: str | None = None  # SHA256 of the original source audio file.
    separation_engine: SeparationEngineInfo | None = None  # Separation engine metadata for the song.
    transcription_runs: list[TranscriptionRun] = Field(default_factory=list)  # Runs used to derive speech and note metadata.
    analysis_settings: dict = Field(default_factory=dict)  # Analysis configuration values for the song.
    artifacts: dict[str, ArtifactEntry] = Field(default_factory=dict)  # Keyed artifact registry entries.
    quality_summary: dict = Field(default_factory=dict)  # Aggregated quality or confidence diagnostics.
    created_at: str | None = None  # ISO8601 creation timestamp for the manifest.
    updated_at: str | None = None  # ISO8601 timestamp of the most recent manifest update.
    model_config = ConfigDict(extra="allow")  # Preserve unknown fields from older or future manifests.

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_payload(cls, data):
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if payload.get("title") is None and payload.get("song_id"):
            payload["title"] = str(payload["song_id"])  # backwards-compatible for older manifests
        if isinstance(payload.get("separation_engine"), str):
            value = payload["separation_engine"]
            payload["separation_engine"] = {
                "name": value,
                "model": value,
                "version": None,
                "profile": "standard",
            }
        return payload

    @field_validator("notes_available", mode="before")
    @classmethod
    def _normalize_notes_available(cls, value):
        if value is None:
            return []
        if isinstance(value, bool):
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @classmethod
    def from_file(cls, path: Path) -> "SongManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(payload)

    def to_file(self, path: Path) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, path)
