import { store } from '../state/store.js';

let activeModule = null;

export function initMetronome(container, state = {}) {
  if (!container) return null;
  const engine = state.metronome;
  if (!engine) return null;
  container.innerHTML = `
    <div class="metronome-panel">
      <div class="metro-pulse" id="metro-pulse" aria-hidden="true"></div>
      <div class="metro-bpm"><span id="metro-bpm-value">120</span><span class="metro-bpm-label">BPM</span></div>
      <div class="metro-controls">
        <button id="metro-toggle" type="button" aria-pressed="false">Enable Click</button>
        <button id="metro-tap" type="button">Tap Tempo</button>
      </div>
    </div>`;
  const pulse = container.querySelector('#metro-pulse');
  const toggle = container.querySelector('#metro-toggle');
  const bpmValue = container.querySelector('#metro-bpm-value');
  const tap = container.querySelector('#metro-tap');
  let taps = [];

  const update = (nextState = store.get()) => {
    const bpm = Number(nextState?.bpm);
    if (Number.isFinite(bpm)) bpmValue.textContent = String(Math.round(bpm));
  };
  const unsubscribe = store.subscribe(update);
  const unsubscribeBeat = engine.onBeat(() => {
    pulse.classList.add('metro-pulse--active');
    setTimeout(() => pulse.classList.remove('metro-pulse--active'), 80);
  });
  toggle.addEventListener('click', () => {
    const enabled = !engine.enabled;
    engine.setEnabled(enabled);
    toggle.textContent = enabled ? 'Disable Click' : 'Enable Click';
    toggle.setAttribute('aria-pressed', String(enabled));
  });
  tap.addEventListener('click', () => {
    const now = performance.now();
    if (taps.length && now - taps[taps.length - 1] > 3000) taps = [];
    taps.push(now);
    if (taps.length > 4) taps.shift();
    if (taps.length === 4) {
      const intervals = taps.slice(1).map((time, index) => time - taps[index]);
      const average = intervals.reduce((sum, interval) => sum + interval, 0) / intervals.length;
      const bpm = 60000 / average;
      if (Number.isFinite(bpm) && bpm > 0) store.set({ bpm: Math.round(bpm) });
    }
  });
  update();
  activeModule = { destroy: () => { unsubscribe(); unsubscribeBeat(); } };
  return activeModule;
}

export function updateMetronome(state) {
  if (state) store.set(state);
}
