import React from 'react';

export function DriveConfigFields({ drivePath, setDrivePath, mwtnFolder, setMwtnFolder }) {
  const handleBrowse = async () => {
    if (window.electronAPI?.selectFolder) {
      try {
        const result = await window.electronAPI.selectFolder();
        if (result?.filePaths && result.filePaths[0]) {
          setDrivePath(result.filePaths[0]);
        }
      } catch (err) {
        console.error('selectFolder error', err);
      }
    }
  };

  return (
    <>
      <div className="sw-form-group">
        <label className="sw-form-label">
          Drive root path
          <input
            type="text"
            className="sw-form-input"
            value={drivePath}
            onChange={(e) => setDrivePath(e.target.value)}
            placeholder="e.g., /Users/you/Google Drive"
          />
        </label>
        <button
          className="sw-btn sw-btn--secondary sw-form-browse-btn"
          onClick={handleBrowse}
          disabled={!window.electronAPI?.selectFolder}
        >
          Browse…
        </button>
      </div>

      <div className="sw-form-group">
        <label className="sw-form-label">
          mwtn output folder name
          <input
            type="text"
            className="sw-form-input"
            value={mwtnFolder}
            onChange={(e) => setMwtnFolder(e.target.value)}
            placeholder="mwtn-outputs"
          />
          <span className="sw-form-hint">Must match the folder name set in your Colab notebook.</span>
        </label>
      </div>
    </>
  );
}

export default DriveConfigFields;
