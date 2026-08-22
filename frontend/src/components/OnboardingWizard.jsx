import React, { useState } from 'react'

export function OnboardingWizard({ onComplete }) {
  const [state, setState] = useState({ step: 1, path: null })

  const go = (next) => setState((s) => ({ ...s, ...next }))

  const StepDots = () => (
    <div className="mwtn-steps">
      {[1, 2, 3].map((n) => (
        <span
          key={n}
          className={`dot ${state.step === n ? 'active' : ''}`}
          aria-hidden
        />
      ))}
    </div>
  )

  return (
    <div className="mwtn-onboarding" role="dialog" aria-modal="true">
      <div className="mwtn-backdrop" />
      <div className="mwtn-modal">
        <StepDots />

        {state.step === 1 && (
          <div className="panel">
            <h2 className="title">Welcome to mwtn</h2>
            <h3 className="subtitle">Moises without the Noises — open-source stem separation for musicians.</h3>
            <p className="lead">Before you can practice, a song needs to be processed into stems. This takes one of two paths depending on your machine.</p>
            <div className="actions">
              <button className="primary" onClick={() => go({ step: 2 })}>
                Choose your setup →
              </button>
            </div>
          </div>
        )}

        {state.step === 2 && (
          <div className="panel">
            <h2 className="title">How will you process songs?</h2>
            <div className="options">
              <div className="card">
                <div className="card-head">
                  <div className="card-label">Docker — run locally</div>
                  <div className="badge">16 GB RAM · Docker Desktop · ffmpeg</div>
                </div>
                <p>Runs Demucs on your machine inside a Docker container. Fully offline after first setup. No GPU? Expect 15–40 min per song on CPU.</p>
                <div className="note warning">⚠ First run downloads ~3.5 GB of model weights. Do this on Wi-Fi.</div>
                <div className="card-actions">
                  <button
                    className="secondary"
                    onClick={() => go({ step: 3, path: 'docker' })}
                  >
                    Set up Docker →
                  </button>
                </div>
              </div>

              <div className="card">
                <div className="card-head">
                  <div className="card-label">Google Colab — free GPU</div>
                  <div className="badge">Google account · Google Drive (optional)</div>
                </div>
                <p>Processes songs on Google's GPU in ~60 seconds. Requires a Google account. Model weights download to Google's servers, not yours.</p>
                <div className="note success">✓ Model weights download on Google's network — not your data plan.</div>
                <div className="card-actions">
                  <button
                    className="secondary"
                    onClick={() => go({ step: 3, path: 'colab' })}
                  >
                    Set up Colab →
                  </button>
                </div>
              </div>
            </div>

            <div className="actions">
              <button className="ghost" onClick={() => go({ step: 1 })}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {state.step === 3 && (
          <div className="panel">
            {state.path === 'docker' ? (
              <>
                <div className="banner warning-banner">First-run data cost: ~3.5 GB. Connect to Wi-Fi before step 3.</div>
                <h2 className="title">Docker — Run locally</h2>
                <ol className="guide">
                  <li>
                    <strong>Install Docker Desktop</strong>
                    <p>Download from <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener noreferrer">docker.com</a> and install for your OS. Make sure it's running before continuing.</p>
                  </li>
                  <li>
                    <strong>Install ffmpeg</strong>
                    <p>On Windows: <code>winget install ffmpeg</code>. On Mac: <code>brew install ffmpeg</code>. On Linux: <code>sudo apt install ffmpeg</code>.</p>
                  </li>
                  <li>
                    <strong>Start the backend</strong>
                    <p>Run <code>run.bat</code> (Windows) or <code>./run.sh</code> (Mac/Linux) from the project root. The first run pulls the Docker image and model weights (~3.5 GB). Do this on Wi-Fi.</p>
                  </li>
                  <li>
                    <strong>Import a song</strong>
                    <p>Click '+ Import a song' in the sidebar. Processing runs locally inside Docker. On CPU, expect 15–40 minutes.</p>
                  </li>
                </ol>
              </>
            ) : (
              <>
                <div className="banner success-banner">Good news: model weights download on Google's network. Your data plan is only used to upload your audio file and download the output zip — typically under 50 MB combined.</div>
                <h2 className="title">Google Colab — Free GPU</h2>
                <ol className="guide">
                  <li>
                    <strong>Open the notebook</strong>
                    <p>Open <a href="https://colab.research.google.com" target="_blank" rel="noopener noreferrer">colab/mwtn_notebook.ipynb</a> in Google Colab.</p>
                  </li>
                  <li>
                    <strong>Enable GPU</strong>
                    <p><em>Runtime → Change runtime type → GPU (T4)</em>. Free tier is sufficient.</p>
                  </li>
                  <li>
                    <strong>Run all cells</strong>
                    <p>Click Runtime → Run all. Demucs and Whisper model weights download to Google's servers on first run (~3.5 GB). This doesn't touch your data plan.</p>
                  </li>
                  <li>
                    <strong>Upload your song</strong>
                    <p>When prompted, upload an audio file (MP3, WAV, FLAC). Processing takes ~60 seconds on GPU.</p>
                  </li>
                  <li>
                    <strong>Download the output zip</strong>
                    <p>Download the zip the notebook produces, then extract it so the song folder is directly inside <code>backend/data/</code>.</p>
                  </li>
                  <li>
                    <strong>Open the app</strong>
                    <p>Start the backend and frontend (see README), then select your song from the sidebar.</p>
                  </li>
                </ol>
              </>
            )}

            <div className="actions final-actions">
              <button className="ghost" onClick={() => go({ step: 2, path: null })}>
                ← Back
              </button>
              <button
                className="primary"
                onClick={() => {
                  if (typeof onComplete === 'function') onComplete()
                }}
              >
                Got it — start using mwtn
              </button>
            </div>
          </div>
        )}

        <style>{`
          .mwtn-onboarding { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
          .mwtn-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000; }
          .mwtn-modal { position: fixed; z-index: 1001; inset: 0; display:flex; align-items:center; justify-content:center; }
          .mwtn-modal > .panel, .mwtn-modal > div > .panel { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 2rem; max-width: 640px; width: 90%; max-height: 85vh; overflow-y: auto; color: #ddd; box-shadow: 0 6px 24px rgba(0,0,0,0.6); }
          .mwtn-steps { display:flex; gap:6px; justify-content:center; margin-bottom:1rem; }
          .dot { width:8px; height:8px; border-radius:50%; background:#555; display:inline-block; }
          .dot.active { background:#fff; }
          .title { color:#fff; margin:0 0 .25rem 0; font-size:1.25rem; }
          .subtitle { color:#bbb; margin:0 0 .75rem 0; font-weight:500; }
          .lead { color:#ccc; margin-bottom:1.25rem; }
          .actions { margin-top:1.25rem; display:flex; gap:.5rem; }
          .final-actions { justify-content:space-between; }
          .primary { background:#111827; color:#fff; border:1px solid #444; padding:.6rem 1rem; border-radius:6px; cursor:pointer; }
          .secondary { background:transparent; color:#fff; border:1px solid #444; padding:.5rem .9rem; border-radius:6px; cursor:pointer; }
          .ghost { background:transparent; color:#bbb; border:1px solid transparent; padding:.4rem .8rem; border-radius:6px; cursor:pointer; }
          .options { display:flex; gap:1rem; align-items:stretch; margin-top:1rem; }
          .card { background:#151515; border:1px solid #2b2b2b; padding:1rem; border-radius:8px; flex:1; display:flex; flex-direction:column; justify-content:space-between; }
          .card-head { display:flex; justify-content:space-between; gap:1rem; align-items:center; margin-bottom:.5rem; }
          .card-label { font-weight:600; color:#fff; }
          .badge { background:#0f172a; color:#9ca3af; padding:.25rem .5rem; border-radius:999px; font-size:.8rem; }
          .note { margin-top:.6rem; padding:.4rem .6rem; border-radius:6px; font-size:.9rem; }
          .note.warning { color:#f59e0b; background: rgba(245,158,11,0.06); }
          .note.success { color:#22c55e; background: rgba(34,197,94,0.06); }
          .banner { padding:.6rem .8rem; border-radius:6px; margin-bottom:1rem; font-weight:600; }
          .warning-banner { color:#f59e0b; background: rgba(245,158,11,0.1); }
          .success-banner { color:#22c55e; background: rgba(34,197,94,0.1); }
          .guide { margin:0; padding-left:1.25rem; }
          .guide li { margin-bottom:.75rem; }
          a { color:#9bdcff; }
          code { background: #0f172a; color:#fff; padding:2px 6px; border-radius:4px; font-family:inherit; }
          @media (max-width:720px) { .options { flex-direction:column; } .mwtn-modal > .panel { padding:1rem; } }
        `}</style>
      </div>
    </div>
  )
}

export default OnboardingWizard
