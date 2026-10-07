/** Transport-synchronised movable-do timeline for the static frontend. */

function el(id) { return document.getElementById(id); }
function setText(id, value) { const node = el(id); if (node) node.textContent = value ?? ''; }

const PIXELS_PER_SECOND = 96;
const MIN_EVENT_WIDTH = 28;
const MIN_REST_WIDTH = 14;
import { getSolfaColour, solfaColoursEnabled } from './utils/solfa.js';

export class SolfaPanel {
  constructor({ API }) {
    this.API = API;
    this._events = [];
    this._current = -1;
    this._loaded = false;
    this._grid = el('solfaGrid');
    this._keyLabel = el('solfaKeyLabel');
    this._nowEl = el('solfaNow');
    this._track = null;
    document.addEventListener('solfa:colours-changed', () => { if (this._loaded) this._renderTimeline(); });
  }

  async loadSong(songId, stemName = 'bass') {
    this._events = [];
    this._current = -1;
    this._loaded = false;
    this._showState('loading');
    try {
      this._ingest(await this.API.getStemSolfa(songId, stemName));
    } catch (error) {
      if (error?.message?.includes('HTTP 404')) this._showState('empty');
      else this._showState('error', error.message);
    }
  }

  tick(currentTime) {
    if (!this._loaded || !this._events.length) return;
    const index = this._findEvent(currentTime);
    if (index === this._current) return;
    this._current = index;
    this._highlightEvent(index);
  }

  clear() {
    this._events = [];
    this._current = -1;
    this._loaded = false;
    this._track = null;
    this._grid?.replaceChildren();
    if (this._nowEl) { this._nowEl.textContent = ''; this._nowEl.style.display = 'none'; }
    if (this._keyLabel) this._keyLabel.textContent = '';
    this._showState('idle');
  }

  _ingest(result) {
    this._events = (result.events || []).map((event) => ({
      onset_s: Number(event.onset_s ?? event.time ?? 0),
      duration_s: Math.max(0, Number(event.duration_s ?? event.duration ?? 0)),
      pitch_midi: event.pitch_midi ?? event.midi ?? null,
      solfa: event.solfa ?? null,
    })).sort((left, right) => left.onset_s - right.onset_s);
    this._loaded = true;
    if (this._keyLabel) this._keyLabel.textContent = `${result.tonic || ''} ${result.mode || ''}`.trim();
    this._renderTimeline();
    this._showState(this._events.length ? 'ready' : 'empty');
  }

  _renderTimeline() {
    if (!this._grid) return;
    this._track = document.createElement('div');
    this._track.className = 'solfa-timeline-track';
    let timelineEnd = 0;
    this._events.forEach((event, index) => {
      const gap = Math.max(0, event.onset_s - timelineEnd);
      if (gap > 0) this._track.appendChild(this._createRestGap(gap));
      this._track.appendChild(this._createEventCell(event, index));
      timelineEnd = Math.max(timelineEnd, event.onset_s + event.duration_s);
    });
    this._grid.replaceChildren(this._track);
  }

  _createRestGap(duration) {
    const gap = document.createElement('div');
    gap.className = 'solfa-rest-gap';
    gap.style.width = `${Math.max(MIN_REST_WIDTH, duration * PIXELS_PER_SECOND)}px`;
    gap.setAttribute('aria-label', `Rest for ${duration.toFixed(2)} seconds`);
    return gap;
  }

  _createEventCell(event, index) {
    const cell = document.createElement('button');
    const isRest = !event.solfa;
    cell.type = 'button';
    cell.className = isRest ? 'solfa-cell solfa-cell-rest' : 'solfa-cell';
    cell.dataset.index = String(index);
    cell.style.width = `${Math.max(isRest ? MIN_REST_WIDTH : MIN_EVENT_WIDTH, event.duration_s * PIXELS_PER_SECOND)}px`;
    cell.title = isRest ? 'Rest' : `${event.solfa} at ${event.onset_s.toFixed(2)} seconds`;
    cell.setAttribute('aria-label', cell.title);
    cell.addEventListener('click', () => document.dispatchEvent(new CustomEvent('solfa:seek', {
      detail: { time: event.onset_s },
    })));
    if (isRest) return cell;

    const syllable = document.createElement('span');
    syllable.className = 'solfa-syl';
    syllable.textContent = event.solfa;
    syllable.style.color = solfaColoursEnabled() ? getSolfaColour(event.solfa) : 'var(--fg)';
    const pitch = document.createElement('span');
    pitch.className = 'solfa-pitch';
    pitch.textContent = event.pitch_midi == null ? '' : `MIDI ${event.pitch_midi}`;
    cell.append(syllable, pitch);
    return cell;
  }

  _findEvent(time) {
    let low = 0;
    let high = this._events.length - 1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      const event = this._events[middle];
      if (time >= event.onset_s && time < event.onset_s + event.duration_s) return middle;
      if (time < event.onset_s) high = middle - 1;
      else low = middle + 1;
    }
    return -1;
  }

  _highlightEvent(index) {
    const previous = this._track?.querySelector('.solfa-cell.active');
    previous?.classList.remove('active');
    if (previous) previous.style.filter = 'none';
    if (index < 0) {
      if (this._nowEl) this._nowEl.style.display = 'none';
      return;
    }
    const cell = this._track?.querySelector(`[data-index="${index}"]`);
    const event = this._events[index];
    if (!cell || !event) return;
    cell.classList.add('active');
    cell.style.filter = solfaColoursEnabled() ? 'brightness(1.3)' : 'none';
    this._centerCell(cell);
    if (this._nowEl) {
      this._nowEl.style.display = '';
      this._nowEl.textContent = event.solfa || 'Rest';
    }
  }

  _centerCell(cell) {
    if (!this._grid || !this._track) return;
    const target = cell.offsetLeft + (cell.offsetWidth / 2) - (this._grid.clientWidth / 2);
    const maximum = Math.max(0, this._track.scrollWidth - this._grid.clientWidth);
    const offset = Math.max(0, Math.min(target, maximum));
    this._track.style.transform = `translateX(${-offset}px)`;
  }

  _showState(state, message = '') {
    const empty = el('solfaEmpty');
    const spinner = el('solfaSpinner');
    const extractButton = el('solfaExtractBtn');
    const error = el('solfaError');
    if (empty) empty.style.display = ['empty', 'error'].includes(state) ? '' : 'none';
    if (spinner) spinner.style.display = state === 'loading' ? '' : 'none';
    if (extractButton) extractButton.style.display = 'none';
    if (error) { error.style.display = state === 'error' ? '' : 'none'; error.textContent = message; }
    if (state === 'loading') setText('solfaPhrase', 'Loading solfège timeline…');
    if (state === 'empty') setText('solfaPhrase', 'No precomputed note events are available for this stem.');
  }
}
