# Extract & Analyse settings guide

Open **Extract & Analyse** from the extraction toolbar. Settings are saved on this device and restored when the panel opens again.

## Separation

Choose a stem model first. The list is loaded from the local backend and includes every model configured for this installation. Each entry shows its name, output count, and description.

The **Stems to Separate** checklist changes with the selected model. Two-stem vocal models only offer their two outputs, while four-, five-, and six-stem models show only their supported stems. Unticking a stem skips writing that WAV file after processing.

Use **Local CPU** to select a local audio file and process it on this machine. It can take 30–90 minutes. Google Colab processing depends on the future Plan 12 queue and currently displays a status message instead of starting an unavailable job.

## Transcription

Enable Whisper to transcribe vocal lyrics. Smaller Whisper models use less storage and run faster; larger ones generally improve accuracy. Select a known language or keep auto-detect.

Note extraction applies only to pitched stems. Lenient confidence retains more candidate notes; strict confidence filters more uncertain notes. A longer minimum duration filters short ornaments.

## Score

Solfège settings select movable/fixed Do, minor-key convention, and coloured syllables. Quantization controls the smallest written rhythm. Confidence review is retained for the forthcoming score-review backend.

## Export

Mix and all-stems exports work for a loaded song. MIDI, MusicXML, and generated click-track exports require the later transcription/export backend and clearly report that limitation.

## Advanced

Papermill and queue settings are retained for the later Colab workflow. They do not start an external process in the current build.
