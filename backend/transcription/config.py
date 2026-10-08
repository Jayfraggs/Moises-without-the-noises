from __future__ import annotations

import importlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schema.units import STEM_ROLES


class TranscriptionConfig(BaseModel):
    """Shared configuration contract for all transcription backends."""

    model_config = ConfigDict(extra="forbid")

    stem_type: str
    quality_profile: Literal["fast", "standard", "high_quality"] = "standard"
    onset_threshold: float = Field(0.5, ge=0.0, le=1.0)
    frame_threshold: float = Field(0.3, ge=0.0, le=1.0)
    minimum_note_length_ms: float = Field(50.0, ge=0.0)
    minimum_frequency_hz: float = Field(32.7, ge=0.0)
    maximum_frequency_hz: float = Field(2093.0, ge=0.0)
    minimum_confidence: float = Field(0.3, ge=0.0, le=1.0)
    chunk_duration_s: float = Field(60.0, gt=0.0)
    chunk_overlap_s: float = Field(2.0, ge=0.0)
    sample_rate: int = 22050
    device: str = "cpu"
    source_model: str = ""

    @field_validator("stem_type")
    @classmethod
    def validate_stem_type(cls, value: str) -> str:
        if value not in STEM_ROLES:
            raise ValueError(f"stem_type must be one of {STEM_ROLES!r}")
        return value

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        if value not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'")
        return value

    @property
    def config_hash(self) -> str:
        import hashlib
        import json

        data = self.model_dump(exclude={"device", "source_model"})
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


ENGINE_REGISTRY: dict[str, dict] = {
    "pyin": {
        "display_name": "pYIN (librosa)",
        "license": "ISC",
        "polyphonic": False,
        "requires_gpu": False,
        "install_check": "librosa",
        "stems": ["vocals", "bass"],
        "profiles": ["fast"],
        "data_cost_mb": 0,
    },
    "basic_pitch": {
        "display_name": "Basic Pitch (Spotify)",
        "license": "MIT",
        "polyphonic": True,
        "requires_gpu": False,
        "install_check": "basic_pitch",
        "stems": ["vocals", "bass", "guitar", "piano", "other"],
        "profiles": ["standard", "high_quality"],
        "data_cost_mb": 67,
    },
    "piano_kong": {
        "display_name": "Piano Transcription (Kong et al.)",
        "license": "MIT",
        "polyphonic": True,
        "requires_gpu": False,
        "install_check": "piano_transcription_inference",
        "stems": ["piano"],
        "profiles": ["high_quality"],
        "data_cost_mb": 350,
        "caveat": "Piano stems only.",
    },
    "adtlib": {
        "display_name": "ADTLib (drum transcription)",
        "license": "MIT",
        "polyphonic": False,
        "requires_gpu": False,
        "install_check": "adtlib",
        "stems": ["drums"],
        "profiles": ["standard", "high_quality"],
        "data_cost_mb": 30,
        "caveat": "Drum stems only.",
    },
    "mt3": {
        "display_name": "MT3 (Google Magenta) — NOT IMPLEMENTED IN V1",
        "license": "Apache-2.0",
        "polyphonic": True,
        "requires_gpu": True,
        "install_check": None,
        "stems": [],
        "profiles": [],
        "data_cost_mb": 2000,
        "caveat": "Deferred to v2. 2 GB checkpoint; JAX dependency.",
        "enabled": False,
    },
}


def is_engine_available(engine_name: str) -> bool:
    """Try-import the engine's install_check module. Returns False if not installed."""
    entry = ENGINE_REGISTRY.get(engine_name, {})
    check = entry.get("install_check")
    if check is None:
        return False
    try:
        importlib.import_module(check)
        return True
    except ImportError:
        return False
