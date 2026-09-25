/**
 * SetupWizard.jsx
 *
 * Standalone full-screen setup wizard — own visual identity distinct from
 * the main mixing-console app. Rendered instead of the main app on first
 * run (useOnboarding hook). Non-dismissible until the user finishes.
 *
 * Visual concept: a dark recording-booth aesthetic — deep charcoal field,
 * amber accent for the active path, teal for interactive elements. Feels
 * like the startup screen of a piece of hardware, not a SaaS modal.
 *
 * Steps:
 *   1  Welcome
 *   2  System scan (auto-advances after 900 ms)
 *   3  Colab info & confirmation
 *   4  Drive for Desktop detection
 *   5  Drive folder configuration (skipped if driveSkipped)
 *   6  Path selection (Colab vs Local — recommendation shown)
 *   7  Step-by-step guide for the chosen path
 */
import React, { useState, useEffect, useRef } from 'react';
import './SetupWizard.css';
import { StepColab } from './wizard/StepColab';
import { StepDriveInstall } from './wizard/StepDriveInstall';
import { StepDriveFolder } from './wizard/StepDriveFolder';

// ---------- System detection -----------------------------------------------

function detectSpecs() {
  return {
    ram: navigator.deviceMemory,           // gigabytes (may be undefined)
    threads: navigator.hardwareConcurrency, // logical CPUs
    platform:
      (navigator.userAgentData && navigator.userAgentData.platform) ||
      navigator.platform ||
      'Unknown',
    effectiveType: navigator.connection?.effectiveType,
    saveData: navigator.connection?.saveData ?? false,
  };
}

function scorePath(specs) {
  const ramOk = specs.ram === undefined || specs.ram >= 16;
  const threadsOk = specs.threads === undefined || specs.threads >= 4;
  const networkOk =
    !specs.saveData &&
    specs.effectiveType !== '2g' &&
    specs.effectiveType !== 'slow-2g';
  return {
    ramOk,
    threadsOk,
    networkOk,
    localViable: ramOk && threadsOk && networkOk,
  };
}

// ---------- Path guide content -----------------------------------------------

const COLAB_STEPS = [
  {
    title: 'Open the notebook',
    body: (
      <>
        Go to{' '}
        <a href="https://colab.research.google.com" target="_blank" rel="noopener noreferrer">
          colab.research.google.com
        </a>{' '}
        and upload <code>colab/mwtn_notebook.ipynb</code> from the project folder.
      </>
    ),
    aside: null,
  },
  {
    title: 'Enable a GPU runtime',
    body: (
      <>
        In the Colab menu: <em>Runtime → Change runtime type → T4 GPU</em>. Without GPU,
        separation takes 10–15× longer.
      </>
    ),
    aside: 'Free tier gives ~2 hours of GPU per session — more than enough for a session.',
  },
  {
    title: 'Run all cells',
    body: (
      <>
        <em>Runtime → Run all</em>. Colab will download ~3.5 GB of model weights to
        Google's servers — not your data plan. Wait for the final cell to show a prompt.
      </>
    ),
    aside: '⚠ This download happens on Colab, not your device.',
  },
  {
    title: 'Upload your audio',
    body: (
      <>
        When the notebook prompts, upload an MP3, WAV, or FLAC file. The notebook runs
        Demucs (6 stems) + Whisper transcription + BPM + key detection in one pass.
      </>
    ),
    aside: 'Uploading the file does use your connection — ~10 MB per minute of audio.',
  },
  {
    title: 'Download the output zip',
    body: (
      <>
        After processing, download the zip from Colab. Extract it so that{' '}
        <code>backend/data/&lt;song_id&gt;/manifest.json</code> exists.
      </>
    ),
    aside: 'The zip is typically 50–200 MB. Do this on Wi-Fi.',
  },
  {
    title: 'Select your song',
    body: (
      <>
        The backend discovers songs automatically once the folder is in place. Refresh
        the sidebar and select your song.
      </>
    ),
    aside: null,
  },
];

const LOCAL_STEPS = [
  {
    title: 'Install Docker Desktop',
    body: (
      <>
        Download{' '}
        <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener noreferrer">
          Docker Desktop
        </a>{' '}
        for your OS and install ffmpeg:
        <br />
        Windows: <code>winget install ffmpeg</code>
        <br />
        macOS: <code>brew install ffmpeg</code>
      </>
    ),
    aside: null,
  },
  {
    title: '⚠ Data warning — do this on Wi-Fi',
    body: (
      <>
        The first run downloads ~3.5 GB of model weights to YOUR machine. Make sure
        you're on an unmetered connection before continuing.
      </>
    ),
    aside: 'Subsequent runs use the cached weights — no re-download.',
    warn: true,
  },
  {
    title: 'Run run.bat or run.ps1',
    body: (
      <>
        From the project root, run <code>run.bat</code> (Windows) or{' '}
        <code>run.ps1</code> (PowerShell). The first run pulls the Docker image and
        model weights; later runs start in seconds.
      </>
    ),
    aside: null,
  },
  {
    title: 'Import a song',
    body: (
      <>
        Once the app loads, use the <strong>+ Import a song</strong> button in the
        sidebar. On a CPU-only laptop expect 15–40 minutes per song. The app remains
        usable during the job.
      </>
    ),
    aside: 'A 4-minute song produces ~200 MB of stems. Keep storage in mind.',
  },
];

// ---------- Components -------------------------------------------------------

function StepIndicator({ current, total }) {
  return (
    <div className="sw-step-indicator" aria-label={`Step ${current} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={`sw-step-dot ${i + 1 === current ? 'sw-step-dot--active' : i + 1 < current ? 'sw-step-dot--done' : ''}`}
        />
      ))}
    </div>
  );
}

function SpecRow({ label, value, ok }) {
  return (
    <div className={`sw-spec-row ${ok === false ? 'sw-spec-row--warn' : ''}`}>
      <span className="sw-spec-label">{label}</span>
      <span className="sw-spec-value">{value ?? '—'}</span>
      {ok === false && <span className="sw-spec-flag">↓</span>}
      {ok === true && <span className="sw-spec-flag sw-spec-flag--ok">✓</span>}
    </div>
  );
}

// ---------- Main wizard ------------------------------------------------------

export function SetupWizard({ onComplete }) {
  const [step, setStep] = useState(1);         // 1..6 (plus substeps in guide)
  const [path, setPath] = useState(null);      // 'colab' | 'local'
  const [subStep, setSubStep] = useState(1);
  const [specs, setSpecs] = useState(null);
  const [driveSkipped, setDriveSkipped] = useState(false);
  const scanRef = useRef(false);

  // Step 2 — auto-scan then advance
  useEffect(() => {
    if (step !== 2 || scanRef.current) return;
    scanRef.current = true;
    const detected = detectSpecs();
    const timer = setTimeout(() => {
      setSpecs(detected);
      setStep(3); // Advance to Colab step
    }, 900);
    return () => clearTimeout(timer);
  }, [step]);

  const score = specs ? scorePath(specs) : null;
  const guideSteps = path === 'colab' ? COLAB_STEPS : LOCAL_STEPS;
  const totalSteps = 6; // Welcome, Scan, Colab, Drive Install, Drive Folder, Path select, then Guide

  function choosePath(chosen) {
    setPath(chosen);
    setSubStep(1);
    // Step 6 is path selection, step 7 starts the guide
    setStep(7);
  }

  function handleDone() {
    localStorage.setItem('mwtn_wizard_complete', 'true');
    if (typeof onComplete === 'function') onComplete();
  }

  return (
    <div className="sw-shell" role="dialog" aria-modal="true" aria-label="mwtn setup wizard">
      <div className="sw-bg" aria-hidden />
      <div className="sw-frame">
        <div className="sw-frame__inner">

          {/* ── Step 1: Welcome ── */}
          {step === 1 && (
            <div className="sw-panel">
              <div className="sw-logo">
                <span className="sw-logo__mark">mwtn</span>
                <span className="sw-logo__sub">Moises without the Noises</span>
              </div>
              <StepIndicator current={1} total={totalSteps} />
              <h1 className="sw-heading">Welcome</h1>
              <p className="sw-body">
                Before you can practice, a song needs to be separated into stems — vocals,
                drums, bass, guitar, and piano as individual tracks.
              </p>
              <p className="sw-body">
                This wizard picks the right path for your machine and walks you through
                the first setup. It only runs once.
              </p>
              <div className="sw-actions">
                <button className="sw-btn sw-btn--primary" onClick={() => { scanRef.current = false; setStep(2); }}>
                  Get started
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: Scanning ── */}
          {step === 2 && (
            <div className="sw-panel sw-panel--center">
              <div className="sw-spinner" aria-label="Scanning system" />
              <p className="sw-scan-label">Checking your system…</p>
            </div>
          )}

          {/* ── Step 3: Colab info ── */}
          {step === 3 && (
            <StepColab
              onNext={() => setStep(4)}
              onBack={() => setStep(1)}
            />
          )}

          {/* ── Step 4: Drive installation ── */}
          {step === 4 && (
            <StepDriveInstall
              onNext={() => setStep(5)}
              onBack={() => setStep(3)}
              onSkip={() => {
                setDriveSkipped(true);
                setStep(6); // Skip directly to path selection
              }}
            />
          )}

          {/* ── Step 5: Drive folder config (skip if driveSkipped) ── */}
          {step === 5 && !driveSkipped && (
            <StepDriveFolder
              onNext={() => setStep(6)}
              onBack={() => setStep(4)}
            />
          )}

          {/* ── Step 6: Path selection ── */}
          {step === 6 && specs && score && (
            <div className="sw-panel">
              <StepIndicator current={5} total={totalSteps} />
              <h2 className="sw-heading">Your system</h2>

              <div className="sw-specs">
                <SpecRow
                  label="RAM"
                  value={specs.ram != null ? `${specs.ram} GB` : 'Unknown'}
                  ok={specs.ram != null ? specs.ram >= 16 : undefined}
                />
                <SpecRow
                  label="CPU threads"
                  value={specs.threads ?? 'Unknown'}
                  ok={specs.threads != null ? specs.threads >= 4 : undefined}
                />
                <SpecRow
                  label="Platform"
                  value={specs.platform}
                />
                <SpecRow
                  label="Network"
                  value={
                    specs.effectiveType
                      ? `${specs.effectiveType}${specs.saveData ? ' · Data Saver on' : ''}`
                      : 'Unknown'
                  }
                  ok={score.networkOk}
                />
              </div>

              <h2 className="sw-heading sw-heading--mt">Choose a processing path</h2>
              <div className="sw-cards">

                {/* Colab card */}
                <div className={`sw-card ${!score.localViable ? 'sw-card--highlight' : ''}`}>
                  {!score.localViable && (
                    <div className="sw-card__badge">Recommended for your system</div>
                  )}
                  <div className="sw-card__title">Google Colab</div>
                  <div className="sw-card__sub">Free GPU · No local install</div>
                  <p className="sw-card__body">
                    Processes songs on Google's GPU in ~60 seconds. Model weights download
                    to Google's servers, not your device. Needs a Google account and an
                    internet connection during processing.
                  </p>
                  <div className="sw-card__note sw-card__note--good">
                    ~3.5 GB downloads on Colab, not your data plan
                  </div>
                  <button
                    className="sw-btn sw-btn--secondary sw-card__cta"
                    onClick={() => choosePath('colab')}
                  >
                    Choose Colab →
                  </button>
                </div>

                {/* Local card */}
                <div className={`sw-card ${score.localViable ? 'sw-card--highlight' : 'sw-card--dim'}`}>
                  {score.localViable && (
                    <div className="sw-card__badge">Your machine can handle this</div>
                  )}
                  <div className="sw-card__title">Run locally</div>
                  <div className="sw-card__sub">Docker · Fully offline after setup</div>
                  <p className="sw-card__body">
                    Runs Demucs on your machine inside Docker. Fully offline after the
                    initial model download. No GPU? Expect 15–40 minutes per song on CPU.
                  </p>
                  {!score.localViable && (
                    <div className="sw-card__note sw-card__note--warn">
                      {!score.ramOk
                        ? `Requires 16 GB RAM — your device reports ${specs.ram ?? '?'} GB`
                        : !score.threadsOk
                        ? `Requires 4 CPU threads — your device reports ${specs.threads ?? '?'}`
                        : 'Constrained network detected — first run downloads 3.5 GB'}
                    </div>
                  )}
                  <button
                    className="sw-btn sw-btn--secondary sw-card__cta"
                    onClick={() => choosePath('local')}
                  >
                    Choose local →
                  </button>
                </div>
              </div>

              <div className="sw-actions sw-actions--left">
                <button className="sw-btn sw-btn--ghost" onClick={() => setStep(driveSkipped ? 4 : 5)}>
                  ← Back
                </button>
              </div>
            </div>
          )}

          {/* ── Step 7: Guide ── */}
          {step === 7 && path && (
            <div className="sw-panel">
              <StepIndicator current={subStep + 5} total={totalSteps + guideSteps.length - 2} />

              <div className="sw-guide-header">
                <div>
                  <h2 className="sw-heading">
                    {path === 'colab' ? 'Google Colab setup' : 'Local setup'}
                  </h2>
                  <p className="sw-guide-progress">
                    Step {subStep} of {guideSteps.length}
                  </p>
                </div>
                <button
                  className="sw-btn sw-btn--ghost"
                  onClick={() => setStep(6)}
                  aria-label="Switch path"
                >
                  Switch ↩
                </button>
              </div>

              <div className={`sw-guide-step ${guideSteps[subStep - 1]?.warn ? 'sw-guide-step--warn' : ''}`}>
                <div className="sw-guide-step__num">{subStep}</div>
                <div className="sw-guide-step__content">
                  <h3 className="sw-guide-step__title">{guideSteps[subStep - 1]?.title}</h3>
                  <p className="sw-guide-step__body">{guideSteps[subStep - 1]?.body}</p>
                  {guideSteps[subStep - 1]?.aside && (
                    <p className="sw-guide-step__aside">{guideSteps[subStep - 1].aside}</p>
                  )}
                </div>
              </div>

              {/* Sub-step progress bar */}
              <div className="sw-progress-track">
                <div
                  className="sw-progress-fill"
                  style={{ width: `${(subStep / guideSteps.length) * 100}%` }}
                />
              </div>

              <div className="sw-actions sw-actions--split">
                <button
                  className="sw-btn sw-btn--ghost"
                  onClick={() => {
                    if (subStep > 1) setSubStep((s) => s - 1);
                    else setStep(6);
                  }}
                >
                  ← {subStep > 1 ? 'Prev' : 'Back'}
                </button>

                {subStep < guideSteps.length ? (
                  <button
                    className="sw-btn sw-btn--primary"
                    onClick={() => setSubStep((s) => s + 1)}
                  >
                    Next →
                  </button>
                ) : (
                  <button className="sw-btn sw-btn--done" onClick={handleDone}>
                    Open mwtn →
                  </button>
                )}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

export default SetupWizard;
