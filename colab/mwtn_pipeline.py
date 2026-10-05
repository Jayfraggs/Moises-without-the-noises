import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import librosa
import numpy as np
import torch
import whisper

# ── Feature flags ─────────────────────────────────────────────────────────────
# Set these to True to enable the optional new features.
# Each requires extra packages — see the comments next to each flag.
RUN_VOCAL_SPLIT      = False   # pip install "audio-separator[cpu]"  (~200 MB model)
RUN_SECTION_DETECT   = False   # pip install allin1                  (~120 MB model)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEMUCS_MODEL = 'htdemucs_6s'
WHISPER_MODEL = 'medium'
WHISPER_LANGUAGE = None
UPLOAD_METHOD = 'drive'  # 'drive' | 'url' | 'widget'
DRIVE_FILE_PATH = 'Music/Dunsin-Oyekan-You-Remain-Thesame-1.mp3'
DIRECT_URL = ''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_input_path() -> Path:
    if UPLOAD_METHOD == 'drive':
        from google.colab import drive

        drive.mount('/content/drive', force_remount=False)
        src = Path('/content/drive/MyDrive') / DRIVE_FILE_PATH
        if not src.exists():
            raise FileNotFoundError(
                f'File not found in Drive: {src}\n'
                'Make sure the file is uploaded to your Google Drive at that path.'
            )

        dest = Path('/content') / src.name
        shutil.copy(src, dest)
        print(f'Loaded from Drive: {src.name}')
        return dest

    if UPLOAD_METHOD == 'url':
        if not DIRECT_URL:
            raise ValueError('Set DIRECT_URL to a direct download link.')

        url_filename = Path(DIRECT_URL.split('?')[0]).name or 'song.mp3'
        dest = Path('/content') / url_filename
        print(f'Downloading {url_filename}...')
        urllib.request.urlretrieve(DIRECT_URL, dest)
        print(f'Downloaded: {dest} ({dest.stat().st_size / 1e6:.1f} MB)')
        return dest

    if UPLOAD_METHOD == 'widget':
        from google.colab import files

        print('A file picker will appear below. Select your file immediately.')
        uploaded = files.upload()
        if not uploaded:
            raise RuntimeError('No file selected.')
        input_filename = list(uploaded.keys())[0]
        print(f'Uploaded: {input_filename}')
        return Path(input_filename)

    raise ValueError(f'Unknown UPLOAD_METHOD: {UPLOAD_METHOD!r}. Use drive, url, or widget.')


def run_demucs(input_path: Path) -> tuple[Path, Path]:
    raw_stem = input_path.stem
    song_id = re.sub(r'[^\w]', '_', raw_stem).strip('_') or 'song'
    demucs_out = Path('_demucs_raw')

    print(f'Song ID: {song_id}')
    print(f'Running Demucs ({DEMUCS_MODEL})...')

    result = subprocess.run(
        [sys.executable, '-m', 'demucs', '-n', DEMUCS_MODEL, '-o', str(demucs_out), str(input_path)],
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError('Demucs failed. Check output above.')

    stems_source_dir = demucs_out / DEMUCS_MODEL / input_path.stem
    stem_wavs = list(stems_source_dir.glob('*.wav'))
    print(f'\nSeparation complete. Stems: {[w.stem for w in stem_wavs]}')
    return song_id, stems_source_dir


def transcribe_lyrics(stems_source_dir: Path):
    vocals_path = stems_source_dir / 'vocals.wav'
    if not vocals_path.exists():
        print('No vocals stem found — skipping transcription.')
        return None

    print(f'Loading Whisper ({WHISPER_MODEL})...')
    whisper_model = whisper.load_model(WHISPER_MODEL)

    print('Transcribing vocals stem...')
    transcribe_kwargs = {
        'word_timestamps': True,
        'verbose': False,
    }
    if WHISPER_LANGUAGE:
        transcribe_kwargs['language'] = WHISPER_LANGUAGE

    result = whisper_model.transcribe(str(vocals_path), **transcribe_kwargs)

    words = []
    for seg in result.get('segments', []):
        for w in seg.get('words', []):
            words.append({
                'start': round(w['start'], 3),
                'end': round(w['end'], 3),
                'word': w['word'].strip(),
            })

    segments = [{
        'start': round(s['start'], 3),
        'end': round(s['end'], 3),
        'text': s['text'].strip(),
    } for s in result.get('segments', [])]

    lyrics_result = {
        'language': result.get('language', 'unknown'),
        'words': words,
        'segments': segments,
    }

    print(f'Language detected: {lyrics_result["language"]}')
    print(f'Words transcribed: {len(words)}')
    if segments:
        print(f'First line: {segments[0]["text"]}')

    del whisper_model
    torch.cuda.empty_cache()
    return lyrics_result


def detect_beats(stems_source_dir: Path):
    beat_stem_priority = ['drums', 'other', 'bass', 'vocals']
    beat_stem_path = None

    for stem_name in beat_stem_priority:
        candidate = stems_source_dir / f'{stem_name}.wav'
        if candidate.exists():
            beat_stem_path = candidate
            print(f'Using {stem_name} stem for BPM detection')
            break

    if not beat_stem_path:
        print('No stem available for BPM detection — skipping.')
        return None

    y, sr = librosa.load(str(beat_stem_path), sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    downbeats = beat_times[::4]

    beats_result = {
        'bpm': round(float(np.squeeze(tempo)), 2),
        'beats': [round(t, 4) for t in beat_times],
        'downbeats': [round(t, 4) for t in downbeats],
    }
    print(f'BPM: {beats_result["bpm"]}')
    print(f'Beat count: {len(beat_times)}')
    return beats_result


def detect_key(stems_source_dir: Path):
    key_stem_priority = ['other', 'vocals', 'guitar', 'piano', 'bass']
    key_stem_path = None

    for stem_name in key_stem_priority:
        candidate = stems_source_dir / f'{stem_name}.wav'
        if candidate.exists():
            key_stem_path = candidate
            print(f'Using {stem_name} stem for key detection')
            break

    if not key_stem_path:
        print('No stem available for key detection — skipping.')
        return None

    y, sr = librosa.load(str(key_stem_path), sr=None, mono=True)
    y_harmonic, _ = librosa.effects.hpss(y)
    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    major_template = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_template = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    best_key, best_mode, best_corr = None, None, -np.inf
    for i in range(12):
        for template, mode in [(major_template, 'major'), (minor_template, 'minor')]:
            corr = np.corrcoef(chroma_mean, np.roll(template, i))[0, 1]
            if corr > best_corr:
                best_corr, best_key, best_mode = corr, i, mode

    root = note_names[best_key]
    key_result = {
        'key': f'{root} {best_mode}',
        'root': root,
        'mode': best_mode,
        'confidence': round(float(best_corr), 3),
    }
    print(f'Key: {key_result["key"]} (confidence: {key_result["confidence"]})')
    return key_result


def extract_note_timeline(audio_path, instrument):
    freq_ranges = {
        'bass': ('C1', 'G4'),
        'vocals': ('C2', 'C6'),
    }
    min_segment_duration = 0.08
    note_change_threshold_semitones = 0.5

    fmin = librosa.note_to_hz(freq_ranges[instrument][0])
    fmax = librosa.note_to_hz(freq_ranges[instrument][1])

    y, sr = librosa.load(audio_path, sr=None, mono=True)
    f0, voiced_flag, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr)
    times = librosa.times_like(f0, sr=sr)

    raw_points = []
    for t, f, voiced in zip(times, f0, voiced_flag):
        if voiced and f is not None and not np.isnan(f):
            raw_points.append((float(t), librosa.hz_to_midi(float(f))))

    if not raw_points:
        return []

    frame_hop = times[1] - times[0] if len(times) > 1 else 0.01
    gap_threshold = frame_hop * 3

    segments = []
    seg_start = raw_points[0][0]
    seg_midi = [raw_points[0][1]]
    prev_t = raw_points[0][0]

    for t, midi in raw_points[1:]:
        avg = sum(seg_midi) / len(seg_midi)
        if abs(midi - avg) <= note_change_threshold_semitones and (t - prev_t) <= gap_threshold:
            seg_midi.append(midi)
        else:
            segments.append((seg_start, prev_t, seg_midi))
            seg_start, seg_midi = t, [midi]
        prev_t = t
    segments.append((seg_start, prev_t, seg_midi))

    cleaned = []
    for start, end, midi_values in segments:
        avg_midi = round(sum(midi_values) / len(midi_values))
        note_name = librosa.midi_to_note(avg_midi)
        duration = end - start
        if cleaned:
            ps, pe, pn, pm = cleaned[-1]
            if duration < min_segment_duration or (note_name == pn and (start - pe) <= gap_threshold):
                cleaned[-1] = (ps, end, pn, pm)
                continue
        cleaned.append((start, end, note_name, avg_midi))

    return [{
        'start': round(s, 3),
        'end': round(e, 3),
        'note': n,
        'midi': m,
    } for s, e, n, m in cleaned]


def run_vocal_split(stems_source_dir: Path) -> dict:
    """
    Second-pass vocal separation: split vocals.wav into
    lead_vocals.wav and backing_vocals.wav using audio-separator.

    Enable with: RUN_VOCAL_SPLIT = True  (and pip install "audio-separator[cpu]")

    Data cost: ~200 MB ONNX model downloaded on first use.
    Cached in ~/.cache/audio-separator/ — re-downloaded each Colab session
    unless you cache the model directory to Google Drive.

    Returns dict mapping stem name → Path.
    """
    vocals_path = stems_source_dir / 'vocals.wav'
    if not vocals_path.exists():
        print('No vocals stem found — skipping vocal split.')
        return {}

    try:
        from audio_separator.separator import Separator
    except ImportError:
        print('audio-separator not installed — skipping vocal split.')
        print('To enable: !pip install "audio-separator[cpu]"')
        return {}

    tmp_out = stems_source_dir / '_vocal_split_raw'
    tmp_out.mkdir(exist_ok=True)

    model_preference = ['UVR-BVE-4B_SN-44100-1', 'UVR_MDXNET_KARA_2']
    stem_files = {}

    for model_name in model_preference:
        try:
            print(f'Loading vocal-split model: {model_name}…')
            sep = Separator(
                model_name=model_name,
                output_dir=str(tmp_out),
                output_format='WAV',
            )
            sep.load_model()
            print('Running vocal split…')
            sep.separate(str(vocals_path))
            output_files = list(tmp_out.glob('*.wav'))
            if output_files:
                for f in output_files:
                    name_lower = f.stem.lower()
                    if 'vocal' in name_lower and 'instrumental' not in name_lower:
                        dest = stems_source_dir / 'lead_vocals.wav'
                        shutil.copy(f, dest)
                        stem_files['lead_vocals'] = dest
                    elif 'instrumental' in name_lower or 'backing' in name_lower or 'bve' in name_lower:
                        dest = stems_source_dir / 'backing_vocals.wav'
                        shutil.copy(f, dest)
                        stem_files['backing_vocals'] = dest
                if stem_files:
                    print(f'Vocal split complete: {list(stem_files.keys())}')
                    break
        except Exception as exc:
            print(f'Model {model_name} failed: {exc} — trying next')

    shutil.rmtree(tmp_out, ignore_errors=True)
    if not stem_files:
        print('Vocal split produced no output.')
    return stem_files


def detect_sections_allin1(stems_source_dir: Path) -> list | None:
    """
    Detect song structure sections using the allin1 model (ISMIR 2023, MIT).

    Enable with: RUN_SECTION_DETECT = True  (and pip install allin1)

    Data cost: ~120 MB model checkpoint downloaded on first use.
    Cached in ~/.cache/allin1/ — not persisted across Colab sessions by default.
    To cache to Drive: set os.environ['HF_HOME'] = '/content/drive/MyDrive/hf_cache'
    before importing allin1.

    Returns a list of raw segment dicts, or None on failure.
    """
    # Pick audio source: prefer harmonically rich stems
    source_pref = ['other', 'vocals', 'guitar', 'piano', 'bass']
    source = None
    for name in source_pref:
        candidate = stems_source_dir / f'{name}.wav'
        if candidate.exists():
            source = candidate
            break
    if source is None:
        for wav in stems_source_dir.glob('*.wav'):
            source = wav
            break
    if source is None:
        print('No stems available for section detection.')
        return None

    try:
        import allin1
    except ImportError:
        print('allin1 not installed — skipping section detection.')
        print('To enable: !pip install allin1')
        return None

    try:
        print(f'Running allin1 section detection on {source.name}…')
        result = allin1.analyze(str(source))
        segments = getattr(result, 'segments', None) or []
        if not segments:
            print('allin1 returned no segments.')
            return None

        # Map allin1 labels to mwtn section kinds
        label_map = {
            'intro': 'intro', 'outro': 'outro', 'verse': 'verse',
            'chorus': 'chorus', 'bridge': 'bridge', 'break': 'break',
            'instrumental': 'inst', 'inst': 'inst', 'solo': 'solo',
            'pre-chorus': 'verse', 'pre_chorus': 'verse',
            'post-chorus': 'verse', 'post_chorus': 'verse',
            'interlude': 'bridge', 'transition': 'break',
        }
        raw = []
        for seg in segments:
            start = float(getattr(seg, 'start', 0))
            end   = float(getattr(seg, 'end', 0))
            label = str(getattr(seg, 'label', 'part'))
            kind  = label_map.get(label.lower().strip(), 'part')
            raw.append({'start': start, 'end': end, 'label': kind})

        print(f'allin1 detected {len(raw)} sections.')
        return raw if len(raw) >= 2 else None

    except Exception as exc:
        print(f'allin1 failed: {exc}')
        return None


def normalize_sections_simple(raw: list, duration: float) -> list:
    """
    Minimal section normalization for the Colab pipeline
    (mirrors the logic in backend/audio/sections.py without the import).
    """
    if not raw or duration < 2:
        return []

    SECTION_NAMES = {
        'intro': 'Intro', 'outro': 'Outro', 'verse': 'Verse', 'chorus': 'Chorus',
        'bridge': 'Bridge', 'break': 'Break', 'inst': 'Instrumental',
        'solo': 'Solo', 'part': 'Part',
    }
    SECTION_COLORS = {
        'intro': '#4a7fff', 'verse': '#00c8a0', 'chorus': '#9a4aff',
        'bridge': '#ff8a20', 'break': '#2ab8e8', 'inst': '#e8c840',
        'solo': '#ff4a90', 'outro': '#00d4d4', 'part': '#8391a5',
    }

    valid_kinds = set(SECTION_NAMES.keys())
    segs = []
    for item in raw:
        kind  = item.get('label', item.get('kind', 'part'))
        if kind not in valid_kinds:
            kind = 'part'
        start = max(0.0, min(duration, float(item.get('start', 0))))
        end   = max(0.0, min(duration, float(item.get('end', duration))))
        if end - start >= 0.5:
            segs.append({'start': start, 'end': end, 'kind': kind})

    segs.sort(key=lambda s: s['start'])
    if len(segs) < 2:
        return []

    segs[0]['start'] = 0.0
    segs[-1]['end']  = duration

    sections = []
    for idx, seg in enumerate(segs, start=1):
        kind = seg['kind']
        sections.append({
            'id':    f'auto-{idx:03d}',
            'name':  SECTION_NAMES.get(kind, kind.title()),
            'kind':  kind,
            'start': round(seg['start'], 3),
            'end':   round(seg['end'],   3),
            'color': SECTION_COLORS.get(kind, '#8391a5'),
        })
    return sections


def build_output(
    song_id: str,
    input_path: Path,
    stems_source_dir: Path,
    lyrics_result,
    beats_result,
    key_result,
    vocal_split_stems: dict | None = None,
    sections_result: list | None = None,
):
    output_dir = Path('output') / song_id
    output_dir.mkdir(parents=True, exist_ok=True)

    stem_files = {}
    for wav in stems_source_dir.glob('*.wav'):
        dest = output_dir / wav.name
        shutil.copy(wav, dest)
        stem_files[wav.stem] = str(dest)
        print(f'Copied stem: {wav.stem}')

    if lyrics_result:
        (output_dir / 'lyrics.json').write_text(json.dumps(lyrics_result))
        print('Wrote lyrics.json')

    if beats_result:
        (output_dir / 'beats.json').write_text(json.dumps(beats_result))
        print(f'Wrote beats.json (BPM: {beats_result["bpm"]})')

    if key_result:
        (output_dir / 'key.json').write_text(json.dumps(key_result))
        print(f'Wrote key.json ({key_result["key"]})')

    notes_by_stem = {}
    for instrument in ['bass', 'vocals']:
        stem_path = stems_source_dir / f'{instrument}.wav'
        if not stem_path.exists():
            print(f'{instrument}: stem not found, skipping note detection')
            continue
        print(f'Extracting notes for {instrument}...')
        timeline = extract_note_timeline(str(stem_path), instrument)
        notes_by_stem[instrument] = timeline
        print(f'  {len(timeline)} segments found')

    notes_available = []
    for instrument, timeline in notes_by_stem.items():
        (output_dir / f'notes_{instrument}.json').write_text(json.dumps(timeline))
        notes_available.append(instrument)
        print(f'Wrote notes_{instrument}.json ({len(timeline)} segments)')

    # ── Vocal split stems ─────────────────────────────────────────────────────
    has_vocal_split = False
    if vocal_split_stems:
        for stem_name, stem_path in vocal_split_stems.items():
            dest = output_dir / f'{stem_name}.wav'
            shutil.copy(stem_path, dest)
            stem_files[stem_name] = str(dest)
            print(f'Copied vocal split stem: {stem_name}')
        has_vocal_split = True

    # ── Sections ──────────────────────────────────────────────────────────────
    has_sections = False
    if sections_result:
        (output_dir / 'sections.json').write_text(json.dumps(sections_result, indent=2))
        print(f'Wrote sections.json ({len(sections_result)} sections)')
        has_sections = True

    manifest = {
        'song_id':         song_id,
        'title':           input_path.stem.replace('_', ' '),
        'stems':           list(stem_files.keys()),
        'notes_available': notes_available,
        'has_lyrics':      lyrics_result is not None,
        'has_beats':       beats_result is not None,
        'has_key':         key_result is not None,
        'has_vocal_split': has_vocal_split,
        'has_sections':    has_sections,
        'bpm':             beats_result['bpm'] if beats_result else None,
        'key':             key_result['key']   if key_result   else None,
        'demucs_model':    DEMUCS_MODEL,
    }
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f'\nManifest written:')
    print(json.dumps(manifest, indent=2))

    DRIVE_OUTPUT_DIR = Path('/content/drive/MyDrive/mwtn_outputs')
    DRIVE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print('\nCreating zip...')
    zip_path = shutil.make_archive(song_id, 'zip', root_dir='output', base_dir=song_id)
    print(f'Zip created: {zip_path} ({Path(zip_path).stat().st_size / 1e6:.1f} MB)')

    drive_zip_dest = DRIVE_OUTPUT_DIR / f'{song_id}.zip'
    shutil.copy(zip_path, drive_zip_dest)
    print(f'\n✓ Saved to Google Drive: My Drive/mwtn_outputs/{song_id}.zip')
    print('Open Google Drive in your browser and download the zip at your convenience.')
    print(f'Extract so that backend/data/{song_id}/manifest.json exists (no extra nesting).')


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    input_path = load_input_path()
    song_id, stems_source_dir = run_demucs(input_path)
    lyrics_result = transcribe_lyrics(stems_source_dir)
    beats_result = detect_beats(stems_source_dir)
    key_result = detect_key(stems_source_dir)

    # ── Vocal split (optional second Demucs pass) ─────────────────────────────
    vocal_split_stems = None
    if RUN_VOCAL_SPLIT:
        print('\n── Vocal split ──────────────────────────────────────────────────')
        vocal_split_stems = run_vocal_split(stems_source_dir)

    # ── Section detection (optional third ML model) ────────────────────────────
    sections_result = None
    if RUN_SECTION_DETECT:
        print('\n── Section detection ─────────────────────────────────────────────')
        raw_sections = detect_sections_allin1(stems_source_dir)
        if raw_sections:
            # Get audio duration for normalization
            try:
                import soundfile as sf
                src = next(stems_source_dir.glob('*.wav'), None)
                dur = float(sf.info(str(src)).frames) / sf.info(str(src)).samplerate if src else 300.0
            except Exception:
                dur = 300.0
            sections_result = normalize_sections_simple(raw_sections, dur)
            print(f'Normalised to {len(sections_result)} sections.')

    build_output(
        song_id, input_path, stems_source_dir,
        lyrics_result, beats_result, key_result,
        vocal_split_stems=vocal_split_stems,
        sections_result=sections_result,
    )


if __name__ == '__main__':
    main()
