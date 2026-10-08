### [SOLFA-COLOUR-01] Bass Solfa Colours — Restore and Extend -DONE

**Target Files:** `frontend/css/main.css` *(modify)*, `frontend/js/ui/solfa.js` *(modify)*, `frontend/js/ui/alignedLyrics.js` *(modify)*, `frontend/js/ui/scorePanel.js` *(modify)*

**Context:** Solfa syllable colours were present previously and removed during the frontend migration. The extract panel settings above expose a `solfa_colours` toggle. Colours apply to all solfa display surfaces: the `SolfaDisplay` lane, the `AlignedLyrics` subtext, and the Score UI solfa mode.

**Objective:**
Restore and standardise solfa syllable colours across all display surfaces, driven by the `solfa_colours` setting in the store.

**Technical Specifications:**

**Colour map — add to `frontend/css/main.css` under `:root`:**
```css
:root {
  /* Solfège syllable colours — movable do */
  --solfa-do:  #f87171;   /* red    — tonic, home */
  --solfa-re:  #fb923c;   /* orange */
  --solfa-mi:  #fbbf24;   /* yellow */
  --solfa-fa:  #34d399;   /* green */
  --solfa-sol: #60a5fa;   /* blue */
  --solfa-la:  #a78bfa;   /* violet */
  --solfa-ti:  #f472b6;   /* pink */
  /* Chromatic alterations — desaturated versions */
  --solfa-ra:  #fca5a5;
  --solfa-me:  #fcd34d;
  --solfa-se:  #6ee7b7;
  --solfa-le:  #93c5fd;
  --solfa-te:  #c4b5fd;
}
```

**JS colour resolver — add to `frontend/js/score/notation.js` (or a shared util):**
```js
export const SOLFA_COLOURS = {
  Do:  'var(--solfa-do)',
  Re:  'var(--solfa-re)',
  Mi:  'var(--solfa-mi)',
  Fa:  'var(--solfa-fa)',
  Sol: 'var(--solfa-sol)',
  La:  'var(--solfa-la)',
  Ti:  'var(--solfa-ti)',
  Ra:  'var(--solfa-ra)',
  Me:  'var(--solfa-me)',
  Se:  'var(--solfa-se)',
  Le:  'var(--solfa-le)',
  Te:  'var(--solfa-te)',
};

export function getSolfaColour(syllable, fallback = 'var(--text-muted)') {
  return SOLFA_COLOURS[syllable] ?? fallback;
}
```

**Apply in `solfa.js` (`SolfaDisplay` lane):**
- Each syllable span: if `store.get().solfa_colours`, set `style.color = getSolfaColour(syllable)`.
- Active syllable: colour is preserved but brightness boosted — add `filter: brightness(1.3)` via inline style or a class.
- If `solfa_colours` is false: all syllables use `var(--text-primary)`, active uses `var(--accent)`.

**Apply in `alignedLyrics.js` (`.lyric-solfa` subtext):**
- The `<sub class="lyric-solfa">Sol</sub>` element already has `color: var(--stem-vocals)` from Plan 09.
- Override: if `solfa_colours` enabled, set `style.color = getSolfaColour(syllable)` inline.
- This makes each subtext label its own colour — visually: word in white, solfa syllable in its colour below it.

**Apply in `scorePanel.js` (Score UI — solfa mode):**
- `NotationPainter.drawSolfaEvent()` already accepts a `color` parameter.
- Pass `getSolfaColour(syllable)` when `solfa_colours` is enabled, otherwise pass `var(--text-primary)`.
- The piano roll note blocks should also use solfa colour when solfa mode is active and `solfa_colours` is on.

**Store integration:**
```js
// In main.js, load from localStorage on boot:
const settings = JSON.parse(localStorage.getItem('mwtn_extract_settings') || '{}');
store.set({ solfa_colours: settings.solfa_colours ?? true });

// When extract panel toggle changes:
store.set({ solfa_colours: newValue });
// All subscribed modules re-render immediately.
```

**Execution Constraints:**
- `getSolfaColour` must be importable by any UI module — put it in `frontend/js/score/notation.js` or a new `frontend/js/utils/solfa.js`. Do not duplicate the map across files.
- Colour changes (toggle on/off) must take effect without a page reload — store subscription triggers re-render in each module.
- CSS variables used throughout — not hardcoded hex in JS (the variables allow future theme overrides).

**Output Request:**
Return the CSS variable additions to `main.css`, the `getSolfaColour` util, and the diff blocks for `solfa.js`, `alignedLyrics.js`, and `scorePanel.js`.
