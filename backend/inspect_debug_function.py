import inspect
from audio.section_detection import _detect_with_librosa
print(inspect.getsource(_detect_with_librosa))
print(_detect_with_librosa.__code__.co_filename)
