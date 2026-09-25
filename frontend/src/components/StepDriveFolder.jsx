/**
 * StepDriveFolder.jsx
 *
 * Configures the Drive root path and mwtn output folder name. Allows manual path
 * entry or browsing for the Drive folder. Validates that the drive path is non-empty
 * before enabling the Next button.
 */
import React, { useState, useEffect } from 'react';
import './SetupWizard.css';

export function StepDriveFolder({ onNext, onBack }) {
  const [drivePath, setDrivePath] = useState('');
  const [mwtnFolder, setMwtnFolder] = useState('mwtn-outputs');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadConfig = async () => {
      setLoading(true);
      setError(null);
      if (window.electronAPI?.getDriveConfig) {
        try {
          const config = await window.electronAPI.getDriveConfig();
          if (config.drivePath) {
            setDrivePath(config.drivePath);
          }
          if (config.mwtnFolder) {
            setMwtnFolder(config.mwtnFolder);
          }
        } catch (err) {
          console.error('Error loading Drive config:', err);
          setError('Failed to load Drive configuration');
        }
      }
      setLoading(false);
    };

    loadConfig();
  }, []);

  const handleBrowse = async () => {
    if (window.electronAPI?.selectFolder) {
      try {
        const result = await window.electronAPI.selectFolder();
        if (result.filePaths && result.filePaths[0]) {
          setDrivePath(result.filePaths[0]);
        }
      } catch (err) {
        console.error('Error selecting folder:', err);
      }
    }
  };

  const handleNext = async () => {
    if (!drivePath.trim()) {
      setError('Drive path is required');
      return;
    }

    if (window.electronAPI?.setDriveConfig) {
      try {
        await window.electronAPI.setDriveConfig(drivePath, mwtnFolder);
        onNext();
      } catch (err) {
        console.error('Error saving Drive config:', err);
        setError('Failed to save Drive configuration');
      }
    } else {
      // In browser context, just proceed
      onNext();
    }
  };

  if (loading) {
    return (
      <div className="sw-panel sw-panel--center">
        <div className="sw-spinner" aria-label="Loading Drive configuration" />
        <p className="sw-scan-label">Loading configuration…</p>
      </div>
    );
  }

  return (
    <div className="sw-panel">
      <h2 className="sw-heading">Configure Drive folder</h2>
      <p className="sw-body">
        Tell mwtn where your Google Drive is located and what folder to watch for
        processed songs from Colab.
      </p>

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
          <span className="sw-form-hint">
            Must match the folder name set in your Colab notebook.
          </span>
        </label>
      </div>

      {error && (
        <div className="sw-error-box">
          <span className="sw-error-icon">⚠</span>
          <p className="sw-error-text">{error}</p>
        </div>
      )}

      <div className="sw-actions sw-actions--split">
        <button className="sw-btn sw-btn--ghost" onClick={onBack}>
          ← Back
        </button>
        <button
          className="sw-btn sw-btn--primary"
          onClick={handleNext}
          disabled={!drivePath.trim()}
        >
          Next →
        </button>
      </div>
    </div>
  );
}

export default StepDriveFolder;
