"""
errors.py — Pipeline failure classification.

Ported from StemDeck app/pipeline/errors.py (Apache-2.0).

classify_failure() maps stderr/exception text to a small set of
user-meaningful causes so error_detail on a failed import can say
something actionable rather than just "audio processing failed".
"""

from __future__ import annotations


class SeparationError(RuntimeError):
    """Demucs (or another separation pass) failed.

    Carries the stderr tail and compute device so callers can preserve
    evidence about what happened.
    """

    def __init__(
        self,
        message: str,
        *,
        tail: list[str] | None = None,
        device: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tail: list[str] = tail or []
        self.device = device


# Ordered — first match wins. Substring against lowercased text.
_CAUSE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "out-of-memory",
        (
            "cuda out of memory",
            "mps backend out of memory",
            "not enough memory",
            "cannot allocate memory",
            "out of memory",
            "memoryerror",
        ),
    ),
    (
        "unsupported-device",
        (
            "no kernel image is available",
            "invalid device",
            "cuda driver version is insufficient",
            "cudnn error",
            "not currently implemented for the mps device",
            "torch not compiled with cuda",
        ),
    ),
    (
        "disk-full",
        (
            "no space left on device",
            "errno 28",
            "disk quota exceeded",
        ),
    ),
    (
        "bad-input",
        (
            "invalid data found",
            "could not open file",
            "unable to open",
            "no stems produced",
            "failed to read",
            "unsupported format",
            "ffmpeg transcode failed",
        ),
    ),
)


def classify_failure(text: str) -> str:
    """Map failure output to one of:
    out-of-memory | unsupported-device | disk-full | bad-input | unknown
    """
    low = text.lower()
    for cause, patterns in _CAUSE_PATTERNS:
        if any(p in low for p in patterns):
            return cause
    return "unknown"
