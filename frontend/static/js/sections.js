/**
 * sections.js — Sections panel editor.
 *
 * Sections are rendered as coloured blocks on the ribbon.
 * Left/right edges are drag-resizable.
 * Double-click opens an inline popup to rename + change kind.
 * "Add" button inserts a new section at the current playhead position.
 * Auto-saves 600 ms after any change.
 */

const SECTION_COLORS = {
  intro:'#4a7fff', verse:'#00c8a0', chorus:'#9a4aff', bridge:'#ff8a20',
  break:'#2ab8e8', inst:'#e8c840', solo:'#ff4a90', outro:'#00d4d4', part:'#8391a5',
};
const SECTION_NAMES = {
  intro:'Intro', verse:'Verse', chorus:'Chorus', bridge:'Bridge',
  break:'Break', inst:'Instrumental', solo:'Solo', outro:'Outro', part:'Part',
};
const KINDS = Object.keys(SECTION_NAMES);

let _idSeq = 1;
function genId() { return `s-${Date.now()}-${_idSeq++}`; }

export class Sections {
  constructor({ State, API, studio }) {
    this.State  = State;
    this.API    = API;
    this.studio = studio;

    this._sections   = [];
    this._saveTimer  = null;
    this._dirty      = false;
    this._trackEl    = document.getElementById('daw-sections-track');
    this._addBtn     = document.getElementById('sectionsAddBtn');
    this._clearBtn   = document.getElementById('sectionsClearBtn');
    this._saveInd    = document.getElementById('sectionsSaveIndicator');
  }

  init() {
    this._addBtn?.addEventListener('click',   () => this._addAtPlayhead());
    this._clearBtn?.addEventListener('click', () => this._clearAll());
    // Show buttons now (they were hidden until a song loads)
    this._addBtn?.classList.remove('hidden');
    this._clearBtn?.classList.remove('hidden');
  }

  loadSong(songId) {
    this._songId   = songId;
    this._sections = (this.State.sections || []).map(s => ({ ...s }));
    this._dirty    = false;
    this._render();
  }

  clear() {
    this._sections = []; this._dirty = false;
    if (this._trackEl) this._trackEl.innerHTML = '';
  }

  // Called from rAF — highlight the active section
  tick(pos) {
    if (!this._sections.length) return;
    this._trackEl?.querySelectorAll('.section-block').forEach(block => {
      const s = parseFloat(block.dataset.start);
      const e = parseFloat(block.dataset.end);
      block.classList.toggle('section-active', pos >= s && pos < e);
    });
  }

  // ── Private: render ───────────────────────────────────────────────────────

  _render() {
    const track = this._trackEl; if (!track) return;
    track.innerHTML = '';
    const dur = this.State.duration;
    if (!dur || !this._sections.length) return;

    this._sections.forEach((sec, idx) => {
      const left  = (sec.start / dur) * 100;
      const width = ((sec.end - sec.start) / dur) * 100;
      const color = SECTION_COLORS[sec.kind] || '#8391a5';

      const block = document.createElement('div');
      block.className = 'section-block';
      block.dataset.idx   = idx;
      block.dataset.start = sec.start;
      block.dataset.end   = sec.end;
      block.style.cssText = `left:${left}%;width:${width}%;--sec-color:${color}`;

      block.innerHTML = `
        <div class="section-drag-edge section-drag-left"  data-role="left"  title="Drag to resize"></div>
        <span class="section-label">${sec.name || SECTION_NAMES[sec.kind] || sec.kind}</span>
        <div class="section-drag-edge section-drag-right" data-role="right" title="Drag to resize"></div>
      `;

      // Double-click → edit popup
      block.querySelector('.section-label').addEventListener('dblclick', (e) => {
        e.stopPropagation();
        this._openEditPopup(idx, block);
      });

      // Click → seek to section start
      block.querySelector('.section-label').addEventListener('click', () => {
        this.studio.seek(sec.start);
      });

      // Right-click → delete
      block.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        if (confirm(`Delete "${sec.name || sec.kind}" section?`)) this._deleteSection(idx);
      });

      // Edge drag
      block.querySelectorAll('.section-drag-edge').forEach(edge => {
        edge.addEventListener('mousedown', (e) => {
          e.stopPropagation(); e.preventDefault();
          this._startEdgeDrag(e, idx, edge.dataset.role, block);
        });
      });

      track.appendChild(block);
    });
  }

  // ── Private: drag edge ────────────────────────────────────────────────────

  _startEdgeDrag(e, idx, role, block) {
    const track = this._trackEl;
    const rect  = track.getBoundingClientRect();
    const dur   = this.State.duration;

    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

    const onMove = (ev) => {
      const frac = clamp((ev.clientX - rect.left) / rect.width, 0, 1);
      const t    = frac * dur;
      const sec  = this._sections[idx];

      if (role === 'left') {
        // Don't overlap previous section
        const prevEnd = idx > 0 ? this._sections[idx - 1].end : 0;
        sec.start = clamp(t, prevEnd, sec.end - 0.5);
      } else {
        const nextStart = idx < this._sections.length - 1 ? this._sections[idx + 1].start : dur;
        sec.end = clamp(t, sec.start + 0.5, nextStart);
      }

      // Live update block geometry
      const left  = (sec.start / dur) * 100;
      const width = ((sec.end - sec.start) / dur) * 100;
      block.style.left  = `${left}%`;
      block.style.width = `${width}%`;
      block.dataset.start = sec.start;
      block.dataset.end   = sec.end;
    };

    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
      this._dirty = true;
      this._debouncedSave();
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }

  // ── Private: edit popup ───────────────────────────────────────────────────

  _openEditPopup(idx, block) {
    document.getElementById('section-edit-popup')?.remove();

    const sec    = this._sections[idx];
    const popup  = document.createElement('div');
    popup.id     = 'section-edit-popup';
    popup.className = 'section-edit-popup';

    popup.innerHTML = `
      <div class="sep-row">
        <label class="sep-lbl">Name</label>
        <input class="sep-input" id="sep-name" type="text" value="${sec.name || ''}" placeholder="${SECTION_NAMES[sec.kind]||sec.kind}">
      </div>
      <div class="sep-row">
        <label class="sep-lbl">Kind</label>
        <select class="sep-select" id="sep-kind">
          ${KINDS.map(k=>`<option value="${k}"${k===sec.kind?' selected':''}>${SECTION_NAMES[k]}</option>`).join('')}
        </select>
      </div>
      <div class="sep-actions">
        <button class="sep-btn sep-delete" id="sep-delete">Delete</button>
        <button class="sep-btn sep-apply"  id="sep-apply">Apply</button>
      </div>
    `;

    // Position below the block
    const rect = block.getBoundingClientRect();
    popup.style.cssText = `position:fixed;top:${rect.bottom+4}px;left:${rect.left}px;z-index:999`;
    document.body.appendChild(popup);

    const close = () => popup.remove();

    popup.querySelector('#sep-apply').addEventListener('click', () => {
      sec.name  = popup.querySelector('#sep-name').value.trim();
      sec.kind  = popup.querySelector('#sep-kind').value;
      sec.color = SECTION_COLORS[sec.kind] || '#8391a5';
      if (!sec.name) sec.name = SECTION_NAMES[sec.kind];
      this._dirty = true;
      this._render();
      this._debouncedSave();
      close();
    });

    popup.querySelector('#sep-delete').addEventListener('click', () => {
      this._deleteSection(idx); close();
    });

    // Close on outside click
    setTimeout(() => document.addEventListener('click', function _close(e) {
      if (!popup.contains(e.target)) { close(); document.removeEventListener('click', _close); }
    }), 50);
  }

  // ── Private: add / delete / clear ─────────────────────────────────────────

  _addAtPlayhead() {
    const dur = this.State.duration; if (!dur) return;
    const pos = this.State.currentTime;

    // Find insertion point — don't overlap existing sections
    const newSec = {
      id:    genId(),
      name:  'Part',
      kind:  'part',
      start: pos,
      end:   Math.min(pos + 30, dur),
      color: SECTION_COLORS.part,
    };

    // Clamp against neighbours
    const after  = this._sections.find(s => s.start >= pos);
    const before = [...this._sections].reverse().find(s => s.end <= pos);
    if (before) newSec.start = Math.max(newSec.start, before.end);
    if (after)  newSec.end   = Math.min(newSec.end, after.start);

    if (newSec.end - newSec.start < 0.5) {
      alert('Not enough space at current position to add a section.'); return;
    }

    this._sections.push(newSec);
    this._sections.sort((a, b) => a.start - b.start);
    this._dirty = true;
    this._render();
    this._debouncedSave();
  }

  _deleteSection(idx) {
    this._sections.splice(idx, 1);
    this._dirty = true;
    this._render();
    this._debouncedSave();
  }

  _clearAll() {
    if (!this._sections.length) return;
    if (!confirm('Clear all sections?')) return;
    this._sections = [];
    this._dirty    = true;
    this._render();
    this._debouncedSave();
  }

  // ── Private: save ─────────────────────────────────────────────────────────

  _debouncedSave() {
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._save(), 600);
  }

  async _save() {
    if (!this._songId || !this._dirty || !this._sections.length) return;
    try {
      await this.API.patchSections(this._songId, this._sections);
      this.State.sections = this._sections.map(s => ({ ...s }));
      this._dirty = false;
      this._flashSaveIndicator();
    } catch (err) {
      console.error('[sections] save failed:', err);
    }
  }

  _flashSaveIndicator() {
    const el = this._saveInd; if (!el) return;
    el.textContent = 'Saved'; el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 1600);
  }
}
