import { API } from '../api.js';
import { store } from '../state/store.js';

let currentPollStop = null;
let currentJobId = null;

const template = () => `<div class="run-panel-overlay" id="run-overlay" hidden><section class="run-panel" role="dialog" aria-modal="true" aria-labelledby="run-title"><header class="run-panel-header"><div><h2 id="run-title">Ready to Process</h2><span class="run-song-title" id="run-song-title"></span></div><button id="run-panel-close" type="button" aria-label="Close">×</button></header><div class="run-paths"><article class="run-path"><h3>Google Colab <small>Recommended · GPU</small></h3><p>Download a pre-configured notebook, fill in your ngrok URL, and run it in Colab.</p><button id="btn-download-notebook" class="run-action-btn run-action-btn--primary" type="button">Download Notebook (.ipynb)</button><ol class="run-instructions" id="colab-instructions"><li>Upload the notebook to colab.research.google.com.</li><li>Fill in <code>BACKEND_URL</code> with your ngrok URL.</li><li>Run all cells.</li></ol></article><article class="run-path"><h3>Copy Parameters</h3><p>Paste the generated parameters into an already-open notebook.</p><button id="btn-copy-params" class="run-action-btn" type="button">Copy Parameters</button><div id="copy-success" class="run-copy-success" hidden>Copied. Paste into the Parameters cell and run all cells.</div><details><summary>Preview parameters</summary><pre id="params-preview-text"></pre></details></article><article class="run-path"><h3>Run Locally</h3><p>Run through Papermill on this machine. CPU processing may take 30–90 minutes.</p><button id="btn-run-local" class="run-action-btn" type="button">Run Locally via Papermill</button><div id="local-status" hidden></div></article></div><div class="run-tracker" id="run-tracker" hidden><h3>Processing Status</h3><div id="tracker-steps"></div><div class="run-tracker-overall"><span id="tracker-status-label">Waiting…</span><span id="tracker-eta"></span></div></div></section></div>`;

function stepIcon(status) { return { pending: '○', running: '●', done: '✓', failed: '×', skipped: '–' }[status] || '?'; }
function statusLabel(status) { return ({ queued: 'Waiting for processing', running: 'Processing', done: 'Done — song is ready', failed: 'Failed', cancelled: 'Cancelled' })[status] || status || 'Waiting'; }

function renderTracker(job) {
  const tracker = document.getElementById('run-tracker');
  if (!tracker) return;
  tracker.hidden = false;
  const steps = document.getElementById('tracker-steps');
  steps.replaceChildren(...(job.steps || []).map((step) => {
    const row = document.createElement('div');
    row.className = `tracker-step tracker-step--${step.status}`;
    row.textContent = `${stepIcon(step.status)} ${step.name}${step.progress_pct == null ? '' : ` ${Math.round(step.progress_pct)}%`}`;
    return row;
  }));
  document.getElementById('tracker-status-label').textContent = statusLabel(job.status);
  document.getElementById('tracker-eta').textContent = job.estimated_duration_s ? `~${Math.round(job.estimated_duration_s / 60)} min` : '';
  if (job.status === 'done' && job.song_id) {
    API.getManifest(job.song_id).then((manifest) => {
      if (!manifest?.has_beats && !manifest?.stems?.length) return;
      if (document.getElementById('load-song-btn')) return;
      const button = document.createElement('button');
      button.id = 'load-song-btn'; button.className = 'run-action-btn run-action-btn--primary'; button.textContent = 'Load Song';
      button.addEventListener('click', () => { store.set({ pendingSongId: job.song_id }); closeRunPanel(); });
      tracker.append(button);
    }).catch(() => {});
  }
}

function startPolling(jobId) {
  let stopped = false;
  const poll = async () => {
    if (stopped) return;
    try {
      const job = await API.getJob(jobId);
      renderTracker(job);
      if (['done', 'failed', 'cancelled'].includes(job.status)) { stopped = true; return; }
    } catch (error) { document.getElementById('tracker-status-label').textContent = `Polling failed: ${error.message}`; }
    if (!stopped) window.setTimeout(poll, 3000);
  };
  poll();
  return () => { stopped = true; };
}

export function closeRunPanel() { if (currentPollStop) currentPollStop(); currentPollStop = null; document.getElementById('run-overlay')?.setAttribute('hidden', ''); }

export function openRunPanel({ songTitle, jobId, paramsText, instructions }) {
  if (!document.getElementById('run-overlay')) document.body.insertAdjacentHTML('beforeend', template());
  const overlay = document.getElementById('run-overlay');
  currentJobId = jobId;
  document.getElementById('run-song-title').textContent = songTitle || '';
  document.getElementById('params-preview-text').textContent = paramsText || '';
  overlay.hidden = false;
  document.getElementById('run-panel-close').onclick = closeRunPanel;
  document.getElementById('btn-copy-params').onclick = async () => { await copyToClipboard(paramsText || ''); document.getElementById('copy-success').hidden = false; document.getElementById('run-tracker').hidden = false; };
  document.getElementById('btn-download-notebook').onclick = async () => {
    const button = document.getElementById('btn-download-notebook'); button.disabled = true;
    try { const result = await API.downloadNotebook(songTitle, '', window._mwtn?.extractSettings || {}); API.triggerBlobDownload(result.blob, result.jobId || jobId); document.getElementById('run-tracker').hidden = false; }
    catch (error) { document.getElementById('tracker-status-label').textContent = error.message; document.getElementById('run-tracker').hidden = false; }
    finally { button.disabled = false; }
  };
  document.getElementById('btn-run-local').onclick = async () => { const button = document.getElementById('btn-run-local'); button.disabled = true; document.getElementById('local-status').hidden = false; try { await API.runLocalJob(currentJobId); document.getElementById('run-tracker').hidden = false; } catch (error) { document.getElementById('local-status').textContent = error.message; } };
  if (instructions?.colab?.length) document.getElementById('colab-instructions').replaceChildren(...instructions.colab.map((text) => { const li = document.createElement('li'); li.textContent = text; return li; }));
  if (currentPollStop) currentPollStop(); currentPollStop = startPolling(jobId);
}

async function copyToClipboard(text) { if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text); const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0'; document.body.append(area); area.select(); document.execCommand('copy'); area.remove(); }
