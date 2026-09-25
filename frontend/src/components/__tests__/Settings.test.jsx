import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react-dom/test-utils';
import Settings from '../Settings';

describe('Settings panel', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('T1: shows desktop-only message when no electronAPI present', async () => {
    vi.stubGlobal('electronAPI', undefined);
    const onClose = vi.fn();
    render(<Settings onClose={onClose} />);
    expect(screen.getByText(/desktop app/i)).toBeInTheDocument();
    // Close button exists
    const closeBtn = screen.getByRole('button', { name: /close/i });
    await userEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('T2: pre-populates fields from getDriveConfig', async () => {
    const mock = {
      getDriveConfig: vi.fn().mockResolvedValue({ drivePath: '/D/Drive', mwtnFolder: 'mwtn-outputs' }),
      setDriveConfig: vi.fn(),
      selectFolder: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mock);

    render(<Settings onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('/D/Drive')).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('mwtn-outputs')).toBeInTheDocument();
  });

  it('T3: Save calls setDriveConfig and shows Saved ✓', async () => {
    const mock = {
      getDriveConfig: vi.fn().mockResolvedValue({ drivePath: '/D/Drive', mwtnFolder: 'mwtn-outputs' }),
      setDriveConfig: vi.fn().mockResolvedValue({}),
      selectFolder: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mock);

    const user = userEvent.setup();
    render(<Settings onClose={() => {}} />);

    await waitFor(() => expect(screen.getByDisplayValue('/D/Drive')).toBeInTheDocument());

    const saveBtn = screen.getByRole('button', { name: /Save/i });
    await user.click(saveBtn);

    expect(mock.setDriveConfig).toHaveBeenCalledWith('/D/Drive', 'mwtn-outputs');
    await waitFor(() => expect(screen.getByText(/Saved ✓/)).toBeInTheDocument());
  });

  it('T4: Saved ✓ disappears after 2s', async () => {
    vi.useFakeTimers();
    const mock = {
      getDriveConfig: vi.fn().mockResolvedValue({ drivePath: '/D/Drive', mwtnFolder: 'mwtn-outputs' }),
      setDriveConfig: vi.fn().mockResolvedValue({}),
      selectFolder: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mock);

    const user = userEvent.setup();

    // Render and ensure initial values loaded
    render(<Settings onClose={() => {}} />);
    await waitFor(() => expect(screen.getByDisplayValue('/D/Drive')).toBeInTheDocument());

    const saveBtn = screen.getByRole('button', { name: /Save/i });

    // Click save inside act so state updates are flushed
    await act(async () => {
      await user.click(saveBtn);
    });

    await waitFor(() => expect(screen.getByText(/Saved ✓/)).toBeInTheDocument());

    // Advance timers 2000ms inside act so React flushes effects
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    // flush microtasks
    await Promise.resolve();
    await waitFor(() => expect(screen.queryByText(/Saved ✓/)).not.toBeInTheDocument());
    vi.useRealTimers();
  });

  it('T5: Close button calls onClose', async () => {
    const mock = {
      getDriveConfig: vi.fn().mockResolvedValue({ drivePath: '/D/Drive', mwtnFolder: 'mwtn-outputs' }),
      setDriveConfig: vi.fn(),
      selectFolder: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mock);
    const onClose = vi.fn();

    render(<Settings onClose={onClose} />);
    await waitFor(() => expect(screen.getByDisplayValue('/D/Drive')).toBeInTheDocument());

    const closeBtn = screen.getByRole('button', { name: /✕/i });
    await userEvent.click(closeBtn);
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('T6: Scan Now triggers handler and shows Scanning…', async () => {
    const mock = {
      getDriveConfig: vi.fn().mockResolvedValue({ drivePath: '/D/Drive', mwtnFolder: 'mwtn-outputs' }),
      setDriveConfig: vi.fn(),
      selectFolder: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mock);

    // Make scanFn return a promise we can control so the button stays in 'Scanning…' state
    let resolveScan;
    const scanPromise = new Promise((res) => { resolveScan = res; });
    const scanFn = vi.fn().mockReturnValue(scanPromise);
    const user = userEvent.setup();
    render(<Settings onClose={() => {}} onScanRequested={scanFn} />);
    await waitFor(() => expect(screen.getByDisplayValue('/D/Drive')).toBeInTheDocument());

    const scanBtn = screen.getByRole('button', { name: /Scan Now/i });
    await user.click(scanBtn);
    expect(scanFn).toHaveBeenCalled();
    // Button should reflect scanning while promise pending
    await waitFor(() => expect(scanBtn).toHaveTextContent(/Scanning/i));
    // Resolve the scan and wait for UI to update
    resolveScan();
    await waitFor(() => expect(scanBtn).toHaveTextContent(/Scan Now/i));
  });
});
