// [CI-02] CountInControl.jsx
import React from 'react';

// [CI-02] Props:
// - onCountInChange(beats: number)
// - isCountingIn: boolean
// - currentCountInBeat: number (1-indexed)
// - totalCountInBeats: number

export default function CountInControl({ onCountInChange, value = 0, isCountingIn = false, currentCountInBeat = 0, totalCountInBeats = 0 }) {
  const options = [0, 1, 2, 4];

  const containerStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontFamily: 'Segoe UI, Helvetica Neue, Arial, sans-serif',
  };

  const groupStyle = {
    display: 'flex',
    background: 'var(--bg-surface, #1a1a1a)',
    border: '1px solid var(--bg-elevated, #242424)',
    borderRadius: 6,
    overflow: 'hidden',
  };

  const btnBase = {
    padding: '6px 10px',
    cursor: 'pointer',
    background: 'transparent',
    color: 'var(--text-primary, #f0f0f0)',
    border: 'none',
    fontSize: 13,
  };

  const badgeWrap = {
    minWidth: 44,
    height: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  };

  const badgeStyle = {
    display: isCountingIn ? 'inline-flex' : 'none',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--accent, #e8a020)',
    color: 'var(--bg-base, #0f0f0f)',
    padding: '6px 8px',
    borderRadius: 4,
    fontFamily: 'SF Mono, Consolas, monospace',
    fontSize: 13,
    transformOrigin: 'center',
  };

  return (
    <div style={containerStyle}>
      <div style={groupStyle} role="tablist" aria-label="Count In">
        {options.map((opt) => {
          return (
            <button
              key={opt}
              onClick={() => onCountInChange && onCountInChange(opt)}
              title={opt === 0 ? 'Off' : `${opt} beat${opt > 1 ? 's' : ''}`}
              aria-pressed={value === opt}
              style={{
                ...btnBase,
                background: value === opt ? 'var(--amber, #e8a020)' : 'transparent',
                color: value === opt ? '#0f0f0f' : 'var(--text-primary, #f0f0f0)',
                fontWeight: value === opt ? 700 : 400,
                padding: '6px 10px',
                borderRight: '1px solid rgba(255,255,255,0.04)',
              }}
            >
              {opt === 0 ? 'Off' : String(opt)}
            </button>
          );
        })}
      </div>

      <div style={badgeWrap}>
        {/* Keep badge mounted to avoid layout shift; show/hide with display */}
        <div
          // Key forces remount on beat change so CSS animation restarts
          key={isCountingIn ? `${currentCountInBeat}` : 'idle'}
          style={badgeStyle}
          className={isCountingIn ? 'countin-badge pulse' : 'countin-badge'}
          aria-hidden={!isCountingIn}
        >
          {isCountingIn ? `${currentCountInBeat} / ${totalCountInBeats}` : ''}
        </div>
      </div>

      <style>{`
        .countin-badge.pulse { animation: countin-pulse 240ms ease-out; }
        @keyframes countin-pulse {
          0% { transform: scale(0.8); opacity: 0.6; }
          50% { transform: scale(1.08); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
