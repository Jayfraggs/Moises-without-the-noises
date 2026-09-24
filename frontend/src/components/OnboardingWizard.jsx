import React, { useState, useEffect } from 'react'

function scoreForLocalPath(specs) {
  // Local Demucs needs: >=16 GB RAM, >=4 threads, not on mobile data
  const ramOk = specs.ram === undefined || specs.ram >= 16
  const threadsOk = specs.threads === undefined || specs.threads >= 4
  const networkOk = !specs.saveData && specs.effectiveType !== '2g' && specs.effectiveType !== 'slow-2g'
  return { ramOk, threadsOk, networkOk, recommended: ramOk && threadsOk && networkOk }
}

export function OnboardingWizard({ onComplete }) {
  const [state, setState] = useState({ step: 1, path: null, subStep: 1 })
  const [specs, setSpecs] = useState(null)

  const go = (next) => setState((s) => ({ ...s, ...next }))

  useEffect(() => {
    if (state.step === 2) {
      const detectSpecs = async () => {
        const detected = {
          ram: navigator.deviceMemory,
          threads: navigator.hardwareConcurrency,
          platform: navigator.platform || (navigator.userAgentData && navigator.userAgentData.platform) || 'Unknown',
          effectiveType: navigator.connection?.effectiveType,
          saveData: navigator.connection?.saveData,
        }
        setSpecs(detected)
        setTimeout(() => go({ step: 3 }), 800)
      }
      detectSpecs()
    }
  }, [state.step])

  const StepDots = () => (
    <div className="mwtn-steps">
      {[1, 2, 3, 4].map((n) => (
        <span
          key={n}
          className={`dot ${state.step === n ? 'active' : ''}`}
          aria-hidden
        />
      ))}
    </div>
  )

  const colabSteps = [
    { title: "Open the notebook", content: <p>Go to <a href="https://colab.research.google.com" target="_blank" rel="noopener noreferrer">Google Colab</a> and upload <code>colab/mwtn_notebook.ipynb</code>.</p> },
    { title: "Enable GPU", content: <p><em>Runtime → Change runtime type → T4 GPU</em>.</p> },
    { title: "Run all cells", content: <p><em>Runtime → Run all</em>. Note: ~3.5 GB downloads on Google's servers, not your data plan.</p> },
    { title: "Upload your audio", content: <p>Upload an MP3, WAV, or FLAC when the notebook prompts.</p> },
    { title: "Download the output zip", content: <p>Extract it so that <code>backend/data/&lt;song_id&gt;/manifest.json</code> exists.</p> },
    { title: "Start the app", content: <p>The backend is already running; select your song from the sidebar.</p> }
  ]
  
  const dockerSteps = [
    { title: "Install prerequisites", content: <p>Install <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener noreferrer">Docker Desktop</a> and ffmpeg (<code>winget install ffmpeg</code> on Windows, <code>brew install ffmpeg</code> on Mac).</p> },
    { title: "⚠️ Data warning", content: <p>First run downloads ~3.5 GB on YOUR network. Do this on Wi-Fi.{specs?.effectiveType ? ` (Detected network: ${specs.effectiveType})` : ''}</p> },
    { title: "Run run.bat / run.ps1", content: <p>First run pulls the Docker image and model weights.</p> },
    { title: "Import a song", content: <p>Use the "+ Import a song" button; expect 15–40 min on CPU.</p> }
  ]

  const currentSubSteps = state.path === 'colab' ? colabSteps : dockerSteps
  const isColabRecommended = specs ? !scoreForLocalPath(specs).recommended : false
  const score = specs ? scoreForLocalPath(specs) : { ramOk: true, threadsOk: true, networkOk: true }

  let localFellShortReason = ''
  if (specs && !score.ramOk) localFellShortReason = `Requires 16 GB RAM — your device reports ${specs.ram} GB`
  else if (specs && !score.threadsOk) localFellShortReason = `Requires 4 threads — your device reports ${specs.threads}`
  else if (specs && !score.networkOk) localFellShortReason = `Requires fast network — you appear to be on a constrained connection`

  return (
    <div className="mwtn-onboarding" role="dialog" aria-modal="true">
      <div className="mwtn-backdrop" />
      <div className="mwtn-modal">
        <div className="mwtn-modal-content">
          <StepDots />

          {state.step === 1 && (
            <div className="panel">
              <h2 className="title">Welcome to mwtn</h2>
              <h3 className="subtitle">Moises without the Noises — open-source stem separation for musicians.</h3>
              <p className="lead">Before you can practice, a song needs to be processed into stems. This takes one of two paths depending on your machine.</p>
              <div className="actions">
                <button className="primary" onClick={() => go({ step: 2 })}>
                  Get started →
                </button>
              </div>
            </div>
          )}

          {state.step === 2 && (
            <div className="panel center-content">
              <div className="spinner"></div>
              <h2 className="title" style={{marginTop: '1rem'}}>Checking your system…</h2>
            </div>
          )}

          {state.step === 3 && (
            <div className="panel">
              <h2 className="title">Your system</h2>
              <div className="specs-summary">
                <div><strong>RAM:</strong> {specs?.ram ? `${specs.ram} GB` : 'Unknown'}</div>
                <div><strong>CPU threads:</strong> {specs?.threads || 'Unknown'}</div>
                <div><strong>Platform:</strong> {specs?.platform || 'Unknown'}</div>
                <div><strong>Network:</strong> {specs?.effectiveType || 'Unknown'}{specs?.saveData ? ' (Data Saver)' : ''}</div>
              </div>

              <h2 className="title" style={{marginTop: '1.5rem'}}>Recommended path</h2>
              <div className="options">
                <div className={`card ${isColabRecommended ? 'highlight-card' : ''}`}>
                  <div className="card-head">
                    <div className="card-label">Google Colab — free GPU</div>
                    {isColabRecommended && <div className="badge recommended-badge">✓ Recommended for your system</div>}
                  </div>
                  <p>Processes songs on Google's GPU in ~60 seconds. Requires a Google account. Model weights download to Google's servers, not yours.</p>
                  {!isColabRecommended && <div className="note success">Also a good option — no local install needed</div>}
                  <div className="card-actions" style={{marginTop: 'auto', paddingTop: '1rem'}}>
                    <button className="secondary" onClick={() => go({ step: 4, path: 'colab', subStep: 1 })}>
                      Choose this →
                    </button>
                  </div>
                </div>

                <div className={`card ${isColabRecommended ? 'greyed-out' : ''}`}>
                  <div className="card-head">
                    <div className="card-label">Docker — run locally</div>
                  </div>
                  <p>Runs Demucs on your machine inside a Docker container. Fully offline after first setup. No GPU? Expect 15–40 min per song on CPU.</p>
                  {isColabRecommended && localFellShortReason && <div className="note warning">⚠ {localFellShortReason}</div>}
                  <div className="card-actions" style={{marginTop: 'auto', paddingTop: '1rem'}}>
                    <button className="secondary" onClick={() => go({ step: 4, path: 'docker', subStep: 1 })}>
                      Choose this →
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

          {state.step === 4 && (
            <div className="panel">
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '1rem'}}>
                <h2 className="title">{state.path === 'colab' ? 'Google Colab — Free GPU' : 'Docker — Run locally'}</h2>
                <span className="subtitle" style={{fontSize: '0.9rem', margin: 0}}>Step {state.subStep} of {currentSubSteps.length}</span>
              </div>
              
              <div className="sub-step-content" style={{minHeight: '120px', marginBottom: '1rem'}}>
                <h3 className="title" style={{fontSize: '1.1rem'}}>{currentSubSteps[state.subStep - 1].title}</h3>
                {currentSubSteps[state.subStep - 1].content}
              </div>

              <div className="actions final-actions" style={{marginTop: 0}}>
                <button className="ghost" onClick={() => {
                  if (state.subStep > 1) {
                    go({ subStep: state.subStep - 1 })
                  } else {
                    go({ step: 3 })
                  }
                }}>
                  ← {state.subStep > 1 ? 'Prev' : 'Back'}
                </button>
                <button
                  className="primary"
                  onClick={() => {
                    if (state.subStep < currentSubSteps.length) {
                      go({ subStep: state.subStep + 1 })
                    } else {
                      if (typeof onComplete === 'function') onComplete()
                    }
                  }}
                >
                  {state.subStep < currentSubSteps.length ? 'Next →' : 'Done — open mwtn'}
                </button>
              </div>
            </div>
          )}
        </div>

        <style>{`
          .mwtn-onboarding { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
          .mwtn-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000; }
          .mwtn-modal { position: fixed; z-index: 1001; inset: 0; display:flex; align-items:center; justify-content:center; }
          .mwtn-modal-content { width: 100%; display: flex; flex-direction: column; align-items: center; }
          .mwtn-modal-content > .panel { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 2rem; max-width: 640px; width: 90%; max-height: 85vh; overflow-y: auto; color: #ddd; box-shadow: 0 6px 24px rgba(0,0,0,0.6); }
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
          .card { background:#151515; border:1px solid #2b2b2b; padding:1rem; border-radius:8px; flex:1; display:flex; flex-direction:column; }
          .card-head { display:flex; justify-content:space-between; gap:1rem; align-items:center; margin-bottom:.5rem; }
          .card-label { font-weight:600; color:#fff; }
          .badge { background:#0f172a; color:#9ca3af; padding:.25rem .5rem; border-radius:999px; font-size:.8rem; }
          .recommended-badge { background: rgba(34,197,94,0.15); color: #4ade80; }
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
          .center-content { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 200px; }
          .spinner { width: 40px; height: 40px; border: 4px solid rgba(255,255,255,0.1); border-left-color: #fff; border-radius: 50%; animation: spin 1s linear infinite; }
          @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          .specs-summary { background: #111; border: 1px solid #222; padding: 1rem; border-radius: 6px; margin-bottom: 1rem; display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
          .highlight-card { border-color: #4ade80; box-shadow: 0 0 10px rgba(74, 222, 128, 0.1); }
          .greyed-out { opacity: 0.6; }
          @media (max-width:720px) { .options { flex-direction:column; } .mwtn-modal-content > .panel { padding:1rem; } .specs-summary { grid-template-columns: 1fr; } }
        `}</style>
      </div>
    </div>
  )
}

export default OnboardingWizard
