import React, { useEffect, useState } from 'react';
import DriveConfigFields from './DriveConfigFields.jsx';

export default function Settings({ onClose, onScanRequested }) {
  const [drivePath, setDrivePath] = useState('');
  const [mwtnFolder, setMwtnFolder] = useState('mwtn-outputs');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedTick, setSavedTick] = useState(false);
  const [scanRunning, setScanRunning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      if (window.electronAPI?.getDriveConfig) {
        try {
          const cfg = await window.electronAPI.getDriveConfig();
          if (cfg?.drivePath) setDrivePath(cfg.drivePath);
          if (cfg?.mwtnFolder) setMwtnFolder(cfg.mwtnFolder);
        } catch (err) {
          console.error('getDriveConfig failed', err);
          setError('Failed to load Drive configuration');
        }
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    if (window.electronAPI?.setDriveConfig) {
      try {
        await window.electronAPI.setDriveConfig(drivePath, mwtnFolder);
        setSavedTick(true);
        setTimeout(() => setSavedTick(false), 2000);
      } catch (err) {
        console.error('setDriveConfig failed', err);
        setError('Failed to save Drive configuration');
      }
    } else {
      setSavedTick(true);
      setTimeout(() => setSavedTick(false), 2000);
    }
    setSaving(false);
  };

  const handleScanNow = async () => {
    setScanRunning(true);
    try {
      // Reuse the import handler exposed by ImportSong via API: POST /api/ingest is server-side ingest.
      // In the desktop app the desired action is to trigger a drive scan in the main process or backend.
      // Here we invoke a passed handler if available (from App) otherwise call electronAPI if present.
      if (typeof onScanRequested === 'function') {
        await onScanRequested();
      } else if (window.electronAPI?.triggerDriveScan) {
        await window.electronAPI.triggerDriveScan();
      } else {
        // As a fallback, call the backend ingest endpoint to attempt a scan (no-op in browser)
        await fetch('/api/ingest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ zip_path: '' }) });
      }
    } catch (err) {
      console.error('Scan failed', err);
    } finally {
      setScanRunning(false);
    }
  };

  // Non-electron environment message
  if (!window.electronAPI) {
    return (
      <div className="export-panel">
        <div className="export-panel__header">
          <h3>Settings</h3>
          <button className="btn" onClick={() => onClose?.()}>✕</button>
        </div>
        <div className="export-panel__body">
          <p>Settings only available in the desktop app.</p>
          <div className="export-panel__actions">
            <button className="btn btn-secondary" onClick={() => onClose?.()}>Close</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="export-panel">
      <div className="export-panel__header">
        <h3>Settings</h3>
        <button className="btn" onClick={() => onClose?.()}>✕</button>
      </div>

      <div className="export-panel__body">
        <h4>Google Drive Integration</h4>

        {loading ? (
          <div className="muted">Loading…</div>
        ) : (
          <>
            <DriveConfigFields
              drivePath={drivePath}
              setDrivePath={setDrivePath}
              mwtnFolder={mwtnFolder}
              setMwtnFolder={setMwtnFolder}
            />

            {error && <div className="error-text">{error}</div>}

            <div className="export-panel__actions">
              <button className="btn btn-secondary" onClick={handleScanNow} disabled={scanRunning}>
                {scanRunning ? 'Scanning…' : 'Scan Now'}
              </button>
              <div style={{ flex: 1 }} />
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {savedTick && <span style={{ color: 'var(--accent)' }}>Saved ✓</span>}
                <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
