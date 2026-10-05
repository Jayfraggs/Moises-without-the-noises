# Plan 08 — MuseScore Integration

## Motive

MuseScore serves as MWTN's high-quality notation rendering and score-editing backend. Rather than implementing a full notation engine inside MWTN (a significant engineering effort), MWTN generates MusicXML/MIDI and hands it to MuseScore for professional engraving and editing.

The integration must be **file-based first**: generate MusicXML and open it in an installed MuseScore application. Deeper integration is deferred until the file-based workflow is stable and well-tested.

---

## MuseScore Version Support

| Version | Notes |
|---|---|
| MuseScore 4.x | Recommended; best MusicXML import; free, open-source (GPL) |
| MuseScore 3.x | Also supported; slightly different CLI flags |
| MuseScore Studio | Cloud-connected variant of MuseScore 4; same file format |

MuseScore is free and open-source (GPL). Users are directed to musescore.org to install it.  
MWTN does not bundle MuseScore.

---

## Process

### 1. Detect whether MuseScore is installed

Check standard installation paths per platform:

**Linux:**
```
/usr/bin/mscore
/usr/bin/mscore4
/usr/local/bin/mscore
~/.local/bin/mscore
```

**macOS:**
```
/Applications/MuseScore 4.app/Contents/MacOS/mscore
/Applications/MuseScore 3.app/Contents/MacOS/mscore
```

**Windows:**
```
C:\Program Files\MuseScore 4\bin\MuseScore4.exe
C:\Program Files\MuseScore 3\bin\MuseScore3.exe
```

Expose detection via:
```
GET /api/tools/musescore
returns: { "installed": true | false, "path": "...", "version": "4.x.x" }
```

### 2. Configurable MuseScore path
Allow users to override the detected path via backend config:
```yaml
# backend/config.yaml
musescore:
  executable: null   # null = auto-detect; or provide explicit path
```

### 3. Score directory
Generated scores are stored in:
```
backend/data/<song_id>/scores/
  melody_v1.xml
  full_score_v1.xml
```
Each file is a versioned artifact in the artifact registry (Plan 07).

### 4. Open in MuseScore action
The Electron shell handles the "Open in MuseScore" action:

```javascript
// electron/main.js
ipcMain.handle('open-in-musescore', async (event, { xmlPath }) => {
  const musescorePath = await detectMuseScore();
  if (!musescorePath) {
    return { success: false, error: 'MuseScore not found' };
  }
  const proc = spawn(musescorePath, [xmlPath], { detached: true, stdio: 'ignore' });
  proc.unref();
  return { success: true };
});
```

For the web (non-Electron) build: offer a download of the MusicXML file with instructions to open it manually.

### 5. Export MusicXML and Export MIDI independently
These should work even when MuseScore is not installed:
- `POST /api/songs/{song_id}/generate/musicxml` → download MusicXML
- `POST /api/songs/{song_id}/generate/midi` → download MIDI
- These are independent of the "Open in MuseScore" action

### 6. Preserve generated score inside the MWTN project
A copy of the generated MusicXML is always kept in the artifact registry regardless of whether the user opens it in MuseScore. This ensures the generation run is recoverable.

### 7. Round-trip support (future / v2)
Optional: MWTN generates MusicXML → user edits in MuseScore → user saves → MWTN imports the edited MusicXML.

**Not implemented in v1.** Reason: MuseScore 4 adds proprietary `.mscz` container format and namespace elements that complicate import. File-based workflow is stable first.

### 8. Never overwrite a user-edited score
The system must distinguish:
- `generated` — produced automatically by MWTN transcription
- `user_edited` — user has manually modified the file in MuseScore

Overwrite protection:
- A `user_edited` score is never overwritten by automatic regeneration
- Regeneration always produces a new versioned file: `full_score_v2.xml`, etc.
- The UI clearly shows which version is generated vs user-edited

### 9. MuseScore command-line batch export (optional, for testing)
MuseScore supports headless export:
```bash
mscore -o output.pdf input.xml
mscore -o output.png input.xml
```
Use this in Plan 14 (testing) to validate MusicXML by rendering it to PDF/PNG automatically.

---

## API Endpoints

```
GET  /api/tools/musescore
     returns: { "installed": bool, "path": str, "version": str }

POST /api/songs/{song_id}/scores/{artifact_id}/open-in-musescore
     (Electron only — triggers IPC to shell)
     returns: { "success": bool, "error": str | null }
```

---

## Files to Create / Modify

```
backend/
  tools/
    musescore.py    # detection, path resolution, version check
```

Modify:
- `backend/main.py` — add MuseScore detection endpoint
- `electron/main.js` — add `open-in-musescore` IPC handler

---

## Colab / Mobile Data Implications

**None.** MuseScore runs locally on the user's machine. The MusicXML file that gets opened is already included in the Colab output zip — no additional data transfer required.

---

## Expected Results

- Users can press one button to open a MWTN transcription as an editable MuseScore document
- MWTN remains fully functional even when MuseScore is not installed (export still works)
- Generated and user-edited scores are clearly distinguished and never confused
- MuseScore acts as a professional engraving and editing environment

---

## Acceptance Criteria

- [ ] Installed MuseScore is detected automatically on all three platforms
- [ ] Users can configure a custom MuseScore path
- [ ] Generated MusicXML opens in MuseScore 4 without errors
- [ ] "Open in MuseScore" works from the Electron desktop build
- [ ] Export MusicXML and Export MIDI work without MuseScore installed
- [ ] User-edited scores are never overwritten by automatic regeneration
- [ ] Detection endpoint returns clear status when MuseScore is absent
