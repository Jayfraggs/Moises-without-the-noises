### [PLAN-07] MIDI + MusicXML Export

**Scope:** Takes the resolved `MusicalEvent` stream (with solfa from Plan 06, rhythm/quantization from Plan 04, key/chord from Plan 05) and derives two canonical export formats — **MIDI** and **MusicXML** — both generated from the `MusicalEvent` model, never from each other. Also covers the frontend export UI extension and Colab pipeline integration.

---

### [P07-BE-01] MIDI Exporter

**Target Files:** `backend/export/midi_exporter.py` *(new)*, `backend/export/__init__.py` *(new)*

**Context:** `MusicalEvent` objects carry `pitch_midi`, `onset_s`, `duration_s`, `velocity` (or a default), and `stem` label. MIDI export maps these to standard MIDI note-on/note-off events. Each stem gets its own MIDI track. The canonical `MusicalEvent` model is the single source — do not read from `notes_*.json` files directly here; the caller loads and passes them.

**Objective:**
Implement `export_midi(stem_events: dict[str, list[MusicalEvent]], tempo_bpm: float, output_path: Path) -> Path` that writes a multi-track MIDI file.

**Technical Specifications:**
- Use `mido` (pure Python, no native deps) — `pip install mido`. Add to `requirements.txt`.
- Track layout:
  - Track 0: Tempo track only (`mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(tempo_bpm))`).
  - Track N (one per stem): stem name as track name, notes from that stem's `MusicalEvent` list.
- MIDI channel assignment (avoid channel 10 — reserved for drums in GM):
  ```
  STEM_CHANNELS = {"vocals": 0, "bass": 1, "guitar": 2, "piano": 3, "other": 4, "drums": 9}
  ```
- Velocity: use `event.velocity` if present (0–127); default to 80.
- Timing: convert `onset_s` / `duration_s` to MIDI ticks using `ticks_per_beat=480` and the track tempo. Formula: `ticks = seconds * (ticks_per_beat * tempo_bpm / 60)`.
- Events within each track must be sorted by onset before emitting delta times.
- Skip rests (`pitch_midi` is None or 0).
- Return the `output_path` on success.
- Full type hints. Raise `ValueError` for empty `stem_events`.

**Execution Constraints:**
- Do not use `pretty_midi` — it pulls in numpy-heavy deps and is harder to install cleanly on Colab.
- Do not write directly to `backend/data/` from this module — caller controls output path.
- No global state.

**Output Request:**
Return only `backend/export/midi_exporter.py`, `backend/export/__init__.py`, and the `mido` line to add to `requirements.txt`.

---

### [P07-BE-02] MusicXML Exporter

**Target Files:** `backend/export/musicxml_exporter.py` *(new)*

**Context:** MusicXML is the interchange format MuseScore, Finale, Sibelius, and most notation tools read natively. It is XML — no binary format, no external lib required beyond stdlib `xml.etree.ElementTree`. Each stem becomes a `<part>`. Rhythm values come from the quantized `duration_beats` field on `MusicalEvent` (Plan 04 contract). Key signature comes from Plan 05.

**Objective:**
Implement `export_musicxml(stem_events: dict[str, list[MusicalEvent]], tempo_bpm: float, key_tonic: str, mode: str, time_signature: tuple[int,int], output_path: Path) -> Path`.

**Technical Specifications:**
- Use `xml.etree.ElementTree` only — zero new dependencies.
- Structure:
  ```xml
  <score-partwise version="4.0">
    <part-list> <!-- one <score-part> per stem --> </part-list>
    <part id="P1"> <!-- vocals -->
      <measure number="1">
        <attributes>
          <divisions>4</divisions>  <!-- quarter note = 4 divisions -->
          <key><fifths>...</fifths><mode>major</mode></key>
          <time><beats>4</beats><beat-type>4</beat-type></time>
          <clef><sign>G</sign><line>2</line></clef>
        </attributes>
        <note>
          <pitch><step>E</step><octave>4</octave></pitch>
          <duration>4</duration>
          <type>quarter</type>
        </note>
      </measure>
    </part>
  </score-partwise>
  ```
- `<divisions>`: use 4 (quarter = 4 divisions, eighth = 2, sixteenth = 1, half = 8, whole = 16).
- Convert `pitch_midi` → `<step>`, `<alter>`, `<octave>` using standard MIDI-to-pitch mapping.
- Convert `duration_beats` (float, from Plan 04) → nearest standard note type + dots. Support: whole, half, quarter, eighth, 16th, dotted variants. Clamp unknowns to quarter.
- Key signature: `<fifths>` from tonic + mode (standard circle-of-fifths integer, -7 to +7).
- Rests: emit `<note><rest/><duration>...</duration><type>...</type></note>`.
- Fill incomplete measures with rests.
- Write with `ET.indent` (Python 3.9+) and `ET.write(output_path, encoding="unicode", xml_declaration=True)`.
- Return `output_path`.

**Execution Constraints:**
- Do not use `music21` — too heavy for Colab cold start and breaks offline constraint.
- Do not import `mido` here — these two exporters are independent.
- `duration_beats` field must already be populated by Plan 04; if missing, fall back to `duration_s * (tempo_bpm / 60)` and log a warning.

**Output Request:**
Return only `backend/export/musicxml_exporter.py`.

---

### [P07-BE-03] Export API Routes

**Target Files:** `backend/main.py` *(add two routes)*

**Context:** The existing export endpoint (`POST /api/songs/{song_id}/export`) handles stem audio mixing. Plan 07 adds two new score export routes that return file downloads.

**Objective:**
Add:
- `GET /api/songs/{song_id}/export/midi` — runs MIDI export, returns `.mid` file download.
- `GET /api/songs/{song_id}/export/musicxml` — runs MusicXML export, returns `.xml` file download.

**Technical Specifications:**
- Both routes:
  - Load all available `notes_<stem>.json` files from `backend/data/{song_id}/`.
  - Load `key.json` for tonic/mode/key_midi.
  - Load `beats.json` for `tempo_bpm` and `time_signature` (default `[4,4]` if absent).
  - Call the respective exporter, writing to a temp path under `backend/data/{song_id}/`.
  - Return `FileResponse` with appropriate `media_type`:
    - MIDI: `audio/midi`, filename `{song_id}.mid`
    - MusicXML: `application/vnd.recordare.musicxml+xml`, filename `{song_id}.xml`
- Cache: if the output file exists and all source JSONs are older (mtime), skip re-export and serve the cached file.
- HTTP 404 if no `notes_*.json` files exist for the song.
- HTTP 500 with structured error JSON `{ "error": "...", "detail": "..." }` on export failure — do not let exceptions bubble as 500 HTML.

**Execution Constraints:**
- Do not block the event loop — wrap exporter calls in `asyncio.to_thread(...)`.
- Maintain existing route structure in `main.py`.

**Output Request:**
Return only the two new route blocks for `main.py`.

---

### [P07-FE-01] Export Panel Extension

**Target Files:** `frontend/src/components/ExportPanel.jsx` *(modify)*

**Context:** `ExportPanel.jsx` currently handles stem audio export (mix, single stem, mix + click). Plan 07 adds MIDI and MusicXML export as a second section in the same panel.

**Objective:**
Add a "Score Export" section to `ExportPanel.jsx` with MIDI and MusicXML download buttons.

**Technical Specifications:**
- New section below existing audio export controls, visually separated by a section divider.
- Two buttons: `Download MIDI` and `Download MusicXML`.
- On click: call `GET /api/songs/{songId}/export/midi` or `.../musicxml`, receive the file as a blob, trigger a browser download via a temporary `<a>` element (`URL.createObjectURL`).
- Loading state per button (disable + show spinner while fetching).
- Error state: inline error message below the button if fetch fails (do not use `alert()`).
- Disabled state with tooltip "Notes not yet extracted" if `manifest.notes_available === false`.

**Execution Constraints:**
- No new npm packages.
- Do not alter existing audio export logic or its state.
- Offline-safe: the download is triggered from a local API call — no external URLs.

**Output Request:**
Return only the modified `ExportPanel.jsx`.

---

### [P07-FE-02] Score Export API Client

**Target Files:** `frontend/src/api.js` *(add two functions)*

**Context:** Consistent with existing `api.js` pattern. File downloads are handled as blob fetches, not JSON.

**Objective:**
Add `downloadMidi(songId)` and `downloadMusicXML(songId)` to `api.js`.

**Technical Specifications:**
- Both return a `Blob` (not parsed JSON).
- Use `response.blob()` after confirming `response.ok`.
- Throw a typed error on non-200 responses, including parsing the error JSON body (`{ error, detail }`) if available.
- No new dependencies.

**Execution Constraints:**
- Do not alter existing exports.

**Output Request:**
Return only the two new function blocks for `api.js`.

---

### [P07-COLAB-01] MIDI + MusicXML Generation in Colab Pipeline

**Target Files:** `colab/mwtn_pipeline.py` *(add section)*, `colab/mwtn_notebook.ipynb` *(add cell)*

**Context:** The Colab pipeline already bundles `notes_*.json`, `key.json`, `beats.json` into the output zip. Plan 07 adds a step that runs both exporters inside Colab and includes `{song_id}.mid` and `{song_id}.xml` in the zip — so the user gets score files immediately without needing to hit the export API endpoints after download.

**Objective:**
Add a Colab cell (after solfa, before zip) that:
1. Installs `mido` if not present (`pip install mido -q`).
2. Inlines or imports `midi_exporter.py` and `musicxml_exporter.py` from the repo clone.
3. Runs both exports for all pitched stems.
4. Writes output files into the song folder.

**Technical Specifications:**
- Guard each export in its own `try/except` — a MusicXML failure must not block MIDI output and vice versa.
- Log success/failure per format with file size.
- Cell must be idempotent.
- **Mobile data note:** `mido` is ~50 KB. One-time Colab install cost only — not re-downloaded on re-run if Colab session is alive.

**Execution Constraints:**
- Do not add `music21` or `pretty_midi`.
- The cell must work on a fresh Colab runtime (assume only `mido` needs installing; everything else is already in the pipeline).

**Output Request:**
Return the new notebook cell as a raw JSON cell block and the corresponding `mwtn_pipeline.py` function.

---

**Bandwidth summary for you:**
- `mido` pip install in Colab: ~50 KB. One-time per Colab session.
- No new model weights. No CDN. No API calls.
- The generated `.mid` and `.xml` files are kilobytes — they bundle into your existing Drive zip at negligible cost.
- The two new frontend export buttons trigger local API calls only — no external network.

**Plan 07 is safe to build on mobile data.** The only network touch is the single `mido` install in Colab, and that only happens once per session.