"""Project-wide runtime compatibility shims.

This repo relies on librosa, which expects the legacy soundfile attributes
``SoundFile`` and ``SoundFileRuntimeError``. Newer soundfile releases still
provide the underlying classes under different names, so we add the legacy
aliases before the audio stack imports them.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import soundfile as _sf
except Exception:  # pragma: no cover - soundfile is required for this project
    _sf = None
else:
    if not hasattr(_sf, "SoundFileRuntimeError"):
        _sf.SoundFileRuntimeError = getattr(_sf, "LibsndfileError", RuntimeError)
    if not hasattr(_sf, "SoundFileError"):
        _sf.SoundFileError = getattr(_sf, "LibsndfileError", RuntimeError)
    if not hasattr(_sf, "SoundFile"):
        _sf.SoundFile = type("SoundFile", (), {})
