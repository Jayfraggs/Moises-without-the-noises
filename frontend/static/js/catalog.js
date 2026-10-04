/**
 * catalog.js — Library list: render, search, select, delete.
 */

export class Catalog {
  constructor({ State, API, Studio }) {
    this.State   = State;
    this.API     = API;
    this.studio  = Studio; // set by app.js after Studio is constructed
    this._searchQ = '';

    this._listEl   = document.getElementById('catalogList');
    this._searchEl = document.getElementById('catalogSearch');
    this._countEl  = document.getElementById('libCount');
    this._trashBtn = document.getElementById('trashBtn');

    this._searchEl?.addEventListener('input', () => {
      this._searchQ = this._searchEl.value.toLowerCase();
      this._render();
    });

    this._trashBtn?.addEventListener('click', () => {
      this.State.viewMode = 'trash';
      this._trashBtn.setAttribute('aria-pressed', 'true');
      this._libBtn?.setAttribute('aria-pressed', 'false');
      this._libBtn?.classList.remove('active');
      this._trashBtn.classList.add('active');
      this._render();
    });

    // Library button — switch back to library view
    this._libBtn = document.querySelector('.rail-library');
    this._libBtn?.addEventListener('click', () => {
      this.State.viewMode = 'library';
      this._libBtn.setAttribute('aria-pressed', 'true');
      this._libBtn.classList.add('active');
      this._trashBtn?.setAttribute('aria-pressed', 'false');
      this._trashBtn?.classList.remove('active');
      this._render();
    });

    // Sidebar drop zone
    const dropZone = document.getElementById('sidebarDropZone');
    dropZone?.addEventListener('click', () => document.getElementById('fileInput')?.click());
  }

  async load() {
    try {
      this.State.songs = await this.API.listSongs();
    } catch (e) {
      console.error('[catalog] failed to load songs:', e);
      this.State.songs = [];
    }
    this._render();
  }

  _render() {
    if (!this._listEl) return;

    const { State } = this;
    let songs = State.songs.filter(s => !State.isTrashed(s.song_id));

    if (State.viewMode === 'trash') {
      songs = State.songs.filter(s => State.isTrashed(s.song_id));
    }

    if (this._searchQ) {
      songs = songs.filter(s =>
        (s.title || s.song_id).toLowerCase().includes(this._searchQ)
      );
    }

    if (this._countEl) {
      this._countEl.textContent = String(songs.length);
    }

    if (songs.length === 0) {
      this._listEl.innerHTML = `
        <div style="padding:16px 12px;text-align:center;color:var(--muted);font-size:11.5px;line-height:1.5">
          ${State.viewMode === 'trash'
            ? 'Trash is empty.'
            : 'No songs yet.<br>Drop a Colab ZIP in the sidebar.'}
        </div>`;
      return;
    }

    this._listEl.innerHTML = '';
    songs.forEach(song => {
      const item = this._buildItem(song);
      this._listEl.appendChild(item);
    });
  }

  _buildItem(song) {
    const { State } = this;
    const isActive    = State.songId === song.song_id;
    const isFavorited = State.isFavorited(song.song_id);
    const isTrashed   = State.isTrashed(song.song_id);

    const el = document.createElement('div');
    el.className = 'daw-lib-item' + (isActive ? ' active' : '');
    el.setAttribute('role', 'listitem');
    el.dataset.songId = song.song_id;

    const stems = (song.stems || []).length;
    const dur   = song.duration_secs
      ? this._fmtDur(song.duration_secs)
      : (song.bpm ? `${Math.round(song.bpm)} BPM` : '');
    const key   = song.key || '';

    el.innerHTML = `
      <div class="lib-cover">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
        </svg>
      </div>
      <div class="lib-meta">
        <div class="t">${this._esc(song.title || song.song_id)}</div>
        <div class="s">${stems} stems${dur ? ` · ${dur}` : ''}${key ? ` · ${key}` : ''}</div>
      </div>
      <div class="lib-actions" style="display:flex;gap:2px;flex-shrink:0;opacity:0;transition:opacity 0.12s">
        <button class="lib-action-btn fav-btn" title="${isFavorited ? 'Unfavorite' : 'Favorite'}" aria-label="${isFavorited ? 'Unfavorite' : 'Favorite'}" style="color:${isFavorited ? 'var(--accent)' : 'var(--muted)'}">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="${isFavorited ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
        </button>
        <button class="lib-action-btn del-btn" title="${isTrashed ? 'Delete forever' : 'Move to trash'}" aria-label="${isTrashed ? 'Delete forever' : 'Move to trash'}" style="color:var(--muted)">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M3 6h18 M8 6V4h8v2 M19 6l-1 14H6L5 6"/>
          </svg>
        </button>
      </div>
      <div class="lib-dot" style="background:${isActive ? '#4caf7d' : 'transparent'};flex-shrink:0"></div>
    `;

    // Show actions on hover
    el.addEventListener('mouseenter', () => {
      const acts = el.querySelector('.lib-actions');
      if (acts) acts.style.opacity = '1';
    });
    el.addEventListener('mouseleave', () => {
      const acts = el.querySelector('.lib-actions');
      if (acts) acts.style.opacity = '0';
    });

    // Select
    el.addEventListener('click', (e) => {
      if (e.target.closest('.lib-action-btn')) return;
      this.selectSong(song.song_id);
    });

    // Favorite
    el.querySelector('.fav-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      State.toggleFavorite(song.song_id);
      this._render();
    });

    // Delete / trash
    el.querySelector('.del-btn')?.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (isTrashed) {
        if (!confirm(`Permanently delete "${song.title || song.song_id}"?`)) return;
        try {
          await this.API.deleteSong(song.song_id);
          State.songs = State.songs.filter(s => s.song_id !== song.song_id);
          State.trashedIds.delete(song.song_id);
          State.saveTrashed();
          if (State.songId === song.song_id && this.studio) {
            this.studio.clearStudio();
          }
        } catch (err) {
          alert(`Delete failed: ${err.message}`);
        }
      } else {
        State.toggleTrashed(song.song_id);
      }
      this._render();
    });

    // Add hover style
    const style = document.createElement('style');
    if (!document.getElementById('lib-item-style')) {
      style.id = 'lib-item-style';
      style.textContent = `
        .daw-lib-item {
          display:flex; align-items:center; gap:10px;
          padding:7px 10px; border-radius:8px; cursor:pointer;
          transition:background 80ms; position:relative;
        }
        .daw-lib-item:hover { background:var(--panel); }
        .daw-lib-item.active { background:linear-gradient(90deg,rgba(244,183,64,.1),var(--panel-2) 60%); }
        .daw-lib-item.active::before {
          content:''; position:absolute; left:0; top:6px; bottom:6px;
          width:3px; border-radius:2px; background:var(--accent);
        }
        .lib-cover {
          width:36px; height:36px; border-radius:6px; background:var(--panel-2);
          display:flex; align-items:center; justify-content:center;
          flex-shrink:0; color:var(--muted);
        }
        .lib-meta { flex:1; min-width:0; }
        .lib-meta .t { font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:var(--fg); }
        .lib-meta .s { font-size:10.5px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .lib-dot { width:8px; height:8px; border-radius:50%; }
        .lib-action-btn { width:22px; height:22px; border-radius:4px; display:flex; align-items:center; justify-content:center; transition:background 80ms; }
        .lib-action-btn:hover { background:var(--panel-3); }
      `;
      document.head.appendChild(style);
    }

    return el;
  }

  async selectSong(songId) {
    const { State, API } = this;

    // Clear active studio immediately so UI doesn't show stale data
    if (this.studio) await this.studio.loadSong(songId);

    // Update active state in list
    State.songId = songId;
    this._render();
  }

  addSong(manifest) {
    const exists = this.State.songs.find(s => s.song_id === manifest.song_id);
    if (!exists) this.State.songs.unshift(manifest);
    else Object.assign(exists, manifest);
    this._render();
  }

  _fmtDur(secs) {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  _esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
}
