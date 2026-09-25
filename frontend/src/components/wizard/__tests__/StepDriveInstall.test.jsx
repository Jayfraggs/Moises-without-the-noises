/**
 * StepDriveInstall.test.jsx
 * Tests for the Drive for Desktop detection step in the setup wizard.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepDriveInstall } from '../../StepDriveInstall';
import { StepColab } from '../../StepColab';

describe('StepColab (smoke test)', () => {
  it('T-Colab-1: renders without crashing', () => {
    const onNext = vi.fn();
    const onBack = vi.fn();
    render(<StepColab onNext={onNext} onBack={onBack} />);
    
    expect(screen.getByText('Set up your processing pipeline')).toBeInTheDocument();
  });

  it('T-Colab-2: Next button disabled when checkbox unchecked', () => {
    const onNext = vi.fn();
    const onBack = vi.fn();
    render(<StepColab onNext={onNext} onBack={onBack} />);
    
    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    expect(nextBtn).toBeDisabled();
  });

  it('T-Colab-3: Next button enabled when checkbox checked', async () => {
    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();
    render(<StepColab onNext={onNext} onBack={onBack} />);
    
    const checkbox = screen.getByRole('checkbox');
    await user.click(checkbox);
    
    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    expect(nextBtn).not.toBeDisabled();
  });
});

describe('StepDriveInstall', () => {
  let mockElectronAPI;

  beforeEach(() => {
    // Mock electronAPI globally
    mockElectronAPI = {
      detectDrive: vi.fn(),
      openExternal: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mockElectronAPI);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  // T1: Mount — detection pending
  it('T1: shows spinner with "Checking…" text while detecting', async () => {
    mockElectronAPI.detectDrive.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    // Spinner should be visible (via aria-label)
    expect(screen.getByLabelText('Detecting Drive for Desktop')).toBeInTheDocument();
    expect(screen.getByText('Checking for Google Drive for Desktop…')).toBeInTheDocument();
    expect(screen.getByText('Scanning your system…')).toBeInTheDocument();
  });

  // T2: Detection resolves found: true
  it('T2: displays success message and path when Drive is detected', async () => {
    mockElectronAPI.detectDrive.mockResolvedValue({
      found: true,
      path: '/Users/test/Google Drive',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    // Wait for detection to complete
    await waitFor(() => {
      expect(screen.getByText('Google Drive for Desktop detected')).toBeInTheDocument();
    });

    expect(screen.getByText(/Drive found at:/)).toBeInTheDocument();
    expect(screen.getByText('/Users/test/Google Drive')).toBeInTheDocument();

    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    expect(nextBtn).not.toBeDisabled();
  });

  // T3: Detection resolves found: false
  it('T3: shows download and check again buttons when Drive not found', async () => {
    mockElectronAPI.detectDrive.mockResolvedValue({
      found: false,
      path: null,
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    await waitFor(() => {
      expect(
        screen.getByText('Google Drive for Desktop not detected')
      ).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Download Drive for Desktop/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Check Again/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Skip for now/i })).toBeInTheDocument();
  });

  // T4: Check Again clicked
  it('T4: calls detectDrive again when "Check Again" is clicked', async () => {
    // First call returns not found
    mockElectronAPI.detectDrive.mockResolvedValueOnce({
      found: false,
      path: null,
    });
    // Second call will return found (simulating user installed Drive)
    mockElectronAPI.detectDrive.mockResolvedValueOnce({
      found: true,
      path: '/Users/test/Google Drive',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();
    const user = userEvent.setup();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    // Wait for initial detection
    await waitFor(() => {
      expect(
        screen.getByText('Google Drive for Desktop not detected')
      ).toBeInTheDocument();
    });

    expect(mockElectronAPI.detectDrive).toHaveBeenCalledTimes(1);

    const checkAgainBtn = screen.getByRole('button', { name: /Check Again/i });
    await user.click(checkAgainBtn);

    // After clicking Check Again, should detect Drive this time
    await waitFor(() => {
      expect(screen.getByText('Google Drive for Desktop detected')).toBeInTheDocument();
    });

    // detectDrive should be called again
    expect(mockElectronAPI.detectDrive).toHaveBeenCalledTimes(2);
  });

  // T5: Skip for now clicked
  it('T5: calls onSkip when "Skip for now" is clicked', async () => {
    mockElectronAPI.detectDrive.mockResolvedValue({
      found: false,
      path: null,
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();
    const user = userEvent.setup();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    await waitFor(() => {
      expect(
        screen.getByText('Google Drive for Desktop not detected')
      ).toBeInTheDocument();
    });

    const skipBtn = screen.getByRole('button', { name: /Skip for now/i });
    await user.click(skipBtn);

    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  // T6: No electronAPI (browser context)
  it('T6: renders without crashing when electronAPI is unavailable', async () => {
    vi.stubGlobal('electronAPI', undefined);

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    // Should show not-found state (fallback behavior)
    await waitFor(() => {
      expect(
        screen.queryByText('Google Drive for Desktop not detected')
      ).toBeInTheDocument();
    });
  });

  // Additional test: Download button opens external URL
  it('opens external link when Download button clicked', async () => {
    mockElectronAPI.detectDrive.mockResolvedValue({
      found: false,
      path: null,
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();
    const user = userEvent.setup();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    await waitFor(() => {
      expect(
        screen.getByText('Google Drive for Desktop not detected')
      ).toBeInTheDocument();
    });

    const downloadBtn = screen.getByRole('button', { name: /Download Drive for Desktop/i });
    await user.click(downloadBtn);

    expect(mockElectronAPI.openExternal).toHaveBeenCalledWith(
      'https://www.google.com/drive/download/'
    );
  });

  // Additional test: Back button navigation
  it('calls onBack when Back button clicked', async () => {
    mockElectronAPI.detectDrive.mockResolvedValue({
      found: false,
      path: null,
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();
    const user = userEvent.setup();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    await waitFor(() => {
      expect(
        screen.getByText('Google Drive for Desktop not detected')
      ).toBeInTheDocument();
    });

    const backBtn = screen.getByRole('button', { name: /← Back/i });
    await user.click(backBtn);

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  // Additional test: Next button navigation after successful detection
  it('calls onNext when Next button clicked after successful detection', async () => {
    mockElectronAPI.detectDrive.mockResolvedValue({
      found: true,
      path: '/Users/test/Google Drive',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const onSkip = vi.fn();
    const user = userEvent.setup();

    render(
      <StepDriveInstall onNext={onNext} onBack={onBack} onSkip={onSkip} />
    );

    await waitFor(() => {
      expect(screen.getByText('Google Drive for Desktop detected')).toBeInTheDocument();
    });

    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    await user.click(nextBtn);

    expect(onNext).toHaveBeenCalledTimes(1);
  });
});
