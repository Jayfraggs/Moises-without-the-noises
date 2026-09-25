/**
 * StepColab.jsx
 * 
 * Explains the Google Colab processing pipeline and provides quick-access buttons
 * to the Colab notebook and setup guide. User must confirm understanding via checkbox
 * before proceeding.
 */
import React, { useState } from 'react';
import './SetupWizard.css';

const COLAB_NOTEBOOK_URL = 'https://colab.research.google.com/github/yourusername/mwtn/blob/main/colab/mwtn_notebook.ipynb';
const SETUP_GUIDE_URL = 'https://github.com/yourusername/mwtn/blob/main/docs/Colab.md';

export function StepColab({ onNext, onBack }) {
  const [confirmed, setConfirmed] = useState(false);

  const openExternal = (url) => {
    if (window.electronAPI?.openExternal) {
      window.electronAPI.openExternal(url);
    } else {
      window.open(url, '_blank');
    }
  };

  return (
    <div className="sw-panel">
      <div className="sw-logo">
        <span className="sw-logo__mark">mwtn</span>
        <span className="sw-logo__sub">Moises without the Noises</span>
      </div>

      <h2 className="sw-heading">Set up your processing pipeline</h2>
      <p className="sw-body">
        mwtn uses Google Colab — free cloud GPU processing — to separate audio into
        individual stems. You don't need to install anything heavy locally. Just open
        the notebook, upload your song, and download the results.
      </p>

      <div className="sw-cta-buttons">
        <button
          className="sw-btn sw-btn--secondary"
          onClick={() => openExternal(COLAB_NOTEBOOK_URL)}
        >
          Open Colab Notebook →
        </button>
        <button
          className="sw-btn sw-btn--secondary"
          onClick={() => openExternal(SETUP_GUIDE_URL)}
        >
          View Setup Guide →
        </button>
      </div>

      <label className="sw-checkbox">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <span>I've opened the notebook and understand the pipeline</span>
      </label>

      <div className="sw-actions sw-actions--split">
        <button className="sw-btn sw-btn--ghost" onClick={onBack}>
          ← Back
        </button>
        <button
          className="sw-btn sw-btn--primary"
          onClick={onNext}
          disabled={!confirmed}
        >
          Next →
        </button>
      </div>
    </div>
  );
}

export default StepColab;
