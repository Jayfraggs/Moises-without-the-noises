/**
 * StepDriveInstall.jsx
 *
 * Detects Google Drive for Desktop installation. If found, shows confirmation.
 * If not found, prompts user to install or skip. Also includes "Check Again" to
 * re-run detection (e.g., after the user installs Drive).
 */
import React, { useState, useEffect } from 'react';
import './SetupWizard.css';

export function StepDriveInstall({ onNext, onBack, onSkip }) {
  const [state, setState] = useState('detecting'); // 'detecting' | 'found' | 'not-found'
  const [drivePath, setDrivePath] = useState(null);

  const detectDrive = async () => {
    setState('detecting');
    if (window.electronAPI?.detectDrive) {
      try {
        const result = await window.electronAPI.detectDrive();
        if (result.found) {
          setDrivePath(result.path);
          setState('found');
        } else {
          setState('not-found');
        }
      } catch (error) {
        console.error('Drive detection error:', error);
        setState('not-found');
      }
    } else {
      // In browser context, assume not found
      setState('not-found');
    }
  };

  useEffect(() => {
    detectDrive();
  }, []);

  const openExternal = (url) => {
    if (window.electronAPI?.openExternal) {
      window.electronAPI.openExternal(url);
    } else {
      window.open(url, '_blank');
    }
  };

  return (
    <div className="sw-panel">
      {state === 'detecting' && (
        <>
          <h2 className="sw-heading">Checking for Google Drive for Desktop…</h2>
          <div className="sw-detecting-panel">
            <div className="sw-spinner" aria-label="Detecting Drive for Desktop" />
            <p className="sw-scan-label">Scanning your system…</p>
          </div>
        </>
      )}

      {state === 'found' && (
        <>
          <h2 className="sw-heading">Google Drive for Desktop detected</h2>
          <div className="sw-status-box sw-status-box--success">
            <div className="sw-status-icon">✓</div>
            <div className="sw-status-text">
              <p className="sw-status-title">Drive found at:</p>
              <p className="sw-status-path">{drivePath}</p>
            </div>
          </div>
          <p className="sw-body">
            This wizard will configure the output folder location in the next step.
          </p>

          <div className="sw-actions sw-actions--split">
            <button className="sw-btn sw-btn--ghost" onClick={onBack}>
              ← Back
            </button>
            <button className="sw-btn sw-btn--primary" onClick={onNext}>
              Next →
            </button>
          </div>
        </>
      )}

      {state === 'not-found' && (
        <>
          <h2 className="sw-heading">Google Drive for Desktop not detected</h2>
          <p className="sw-body">
            Google Drive for Desktop syncs your Colab output directly to this machine.
            Install it to automatically receive processed songs without manual downloads.
          </p>

          <div className="sw-actions">
            <button
              className="sw-btn sw-btn--secondary"
              onClick={() => openExternal('https://www.google.com/drive/download/')}
            >
              Download Drive for Desktop →
            </button>
          </div>

          <p className="sw-body">
            After installing, come back to this wizard and click "Check Again".
          </p>

          <div className="sw-actions sw-actions--split">
            <button className="sw-btn sw-btn--ghost" onClick={onBack}>
              ← Back
            </button>
            <div className="sw-actions-group">
              <button
                className="sw-btn sw-btn--secondary"
                onClick={detectDrive}
              >
                Check Again
              </button>
              <button
                className="sw-btn sw-btn--primary"
                onClick={onSkip}
              >
                Skip for now →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default StepDriveInstall;
