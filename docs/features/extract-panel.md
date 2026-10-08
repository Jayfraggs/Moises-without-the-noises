# Extract & Analyse panel

The vanilla frontend extract panel provides a five-tab settings surface for separation, transcription, score generation, export, and advanced job/storage options.

It is implemented in `frontend/js/ui/extractPanel.js` and `frontend/css/extract-panel.css`. Settings persist as the flat `mwtn_extract_settings` local-storage object. The panel is opened by the existing extraction toolbar trigger or by dispatching `extract:open`; a job queue can open it through the same event without coupling the panel to queue internals.

The local path preserves the existing `fileInput` flow. The Colab path currently reports an inline Plan 12 status. Export actions use existing Studio/API owners where available and report clear inline status for future score exports.

Until the Plan 12 backend exists, the Colab, MIDI, MusicXML, and click-track actions are intentionally UI stubs with inline status messages. Existing mix and all-stems exports use the current Studio/API implementation.
