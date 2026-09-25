/**
 * StepDriveFolder.test.jsx
 * Tests for the Drive folder configuration step in the setup wizard.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StepDriveFolder } from '../../StepDriveFolder';

describe('StepDriveFolder', () => {
  let mockElectronAPI;

  beforeEach(() => {
    mockElectronAPI = {
      getDriveConfig: vi.fn(),
      setDriveConfig: vi.fn(),
      selectFolder: vi.fn(),
    };
    vi.stubGlobal('electronAPI', mockElectronAPI);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  // T1: Mount — pre-populates from getDriveConfig
  it('T1: pre-populates fields from saved config on mount', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'my-music-stems',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      const drivePathInput = screen.getByDisplayValue('/Users/test/Google Drive');
      expect(drivePathInput).toBeInTheDocument();
    });

    const mwtnFolderInput = screen.getByDisplayValue('my-music-stems');
    expect(mwtnFolderInput).toBeInTheDocument();
  });

  // T2: drivePath empty — Next disabled
  it('T2: disables Next button when Drive path is empty', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '',
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      const nextBtn = screen.getByRole('button', { name: /Next →/i });
      expect(nextBtn).toBeDisabled();
    });
  });

  // T3: drivePath filled — Next enabled
  it('T3: enables Next button when Drive path is filled', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      const nextBtn = screen.getByRole('button', { name: /Next →/i });
      expect(nextBtn).not.toBeDisabled();
    });
  });

  // T4: Next clicked — calls setDriveConfig and onNext
  it('T4: calls setDriveConfig with correct values and onNext when Next clicked', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'mwtn-outputs',
    });
    mockElectronAPI.setDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(
        screen.getByDisplayValue('/Users/test/Google Drive')
      ).toBeInTheDocument();
    });

    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    await user.click(nextBtn);

    expect(mockElectronAPI.setDriveConfig).toHaveBeenCalledWith(
      '/Users/test/Google Drive',
      'mwtn-outputs'
    );

    await waitFor(() => {
      expect(onNext).toHaveBeenCalledTimes(1);
    });
  });

  // T5: Browse clicked — selectFolder called, path populated
  it('T5: populates Drive path field when Browse button is clicked', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '',
      mwtnFolder: 'mwtn-outputs',
    });
    mockElectronAPI.selectFolder.mockResolvedValue({
      filePaths: ['/Users/newpath/Google Drive'],
      canceled: false,
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\., \/Users/)).toBeInTheDocument();
    });

    const browseBtn = screen.getByRole('button', { name: /Browse…/i });
    await user.click(browseBtn);

    expect(mockElectronAPI.selectFolder).toHaveBeenCalled();

    await waitFor(() => {
      const drivePathInput = screen.getByDisplayValue('/Users/newpath/Google Drive');
      expect(drivePathInput).toBeInTheDocument();
    });
  });

  // T6: getDriveConfig returns defaults
  it('T6: shows default mwtnFolder value when no config exists', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: null,
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      const mwtnFolderInput = screen.getByDisplayValue('mwtn-outputs');
      expect(mwtnFolderInput).toBeInTheDocument();
    });
  });

  // Additional test: User changes input values
  it('allows user to edit Drive path field', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '',
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\., \/Users/)).toBeInTheDocument();
    });

    const drivePathInput = screen.getByPlaceholderText(/e\.g\., \/Users/);
    await user.clear(drivePathInput);
    await user.type(drivePathInput, '/new/path');

    expect(drivePathInput).toHaveValue('/new/path');
  });

  // Additional test: User changes mwtnFolder field
  it('allows user to edit mwtnFolder field', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('mwtn-outputs')).toBeInTheDocument();
    });

    const mwtnFolderInput = screen.getByDisplayValue('mwtn-outputs');
    await user.clear(mwtnFolderInput);
    await user.type(mwtnFolderInput, 'custom-folder');

    expect(mwtnFolderInput).toHaveValue('custom-folder');
  });

  // Additional test: Back button navigation
  it('calls onBack when Back button is clicked', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'mwtn-outputs',
    });

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(
        screen.getByDisplayValue('/Users/test/Google Drive')
      ).toBeInTheDocument();
    });

    const backBtn = screen.getByRole('button', { name: /← Back/i });
    await user.click(backBtn);

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  // Additional test: Browse button disabled when selectFolder not available
  it('disables Browse button when selectFolder IPC is unavailable', async () => {
    vi.stubGlobal('electronAPI', {
      getDriveConfig: vi.fn().mockResolvedValue({
        drivePath: '',
        mwtnFolder: 'mwtn-outputs',
      }),
      setDriveConfig: vi.fn(),
      selectFolder: undefined,
    });

    const onNext = vi.fn();
    const onBack = vi.fn();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      const browseBtn = screen.getByRole('button', { name: /Browse…/i });
      expect(browseBtn).toBeDisabled();
    });
  });

  // Additional test: No electronAPI (browser context)
  it('renders and works without electronAPI in browser context', async () => {
    vi.stubGlobal('electronAPI', undefined);

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\., \/Users/)).toBeInTheDocument();
    });

    // User can type in the field
    const drivePathInput = screen.getByPlaceholderText(/e\.g\., \/Users/);
    await user.type(drivePathInput, '/Users/test');

    // Next button should be enabled and clickable
    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    expect(nextBtn).not.toBeDisabled();
    await user.click(nextBtn);

    // onNext should be called (without calling IPC)
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  // Additional test: Shows error when config load fails
  it('handles error when getDriveConfig fails gracefully', async () => {
    mockElectronAPI.getDriveConfig.mockRejectedValue(
      new Error('Config load failed')
    );

    const onNext = vi.fn();
    const onBack = vi.fn();

    // Should not crash and should show empty fields
    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\., \/Users/)).toBeInTheDocument();
    });
  });

  // Additional test: Shows error when setDriveConfig fails
  it('shows error message when setDriveConfig fails', async () => {
    mockElectronAPI.getDriveConfig.mockResolvedValue({
      drivePath: '/Users/test/Google Drive',
      mwtnFolder: 'mwtn-outputs',
    });
    mockElectronAPI.setDriveConfig.mockRejectedValue(
      new Error('Failed to save config')
    );

    const onNext = vi.fn();
    const onBack = vi.fn();
    const user = userEvent.setup();

    render(<StepDriveFolder onNext={onNext} onBack={onBack} />);

    await waitFor(() => {
      expect(
        screen.getByDisplayValue('/Users/test/Google Drive')
      ).toBeInTheDocument();
    });

    const nextBtn = screen.getByRole('button', { name: /Next →/i });
    await user.click(nextBtn);

    await waitFor(() => {
      expect(screen.getByText(/Failed to save Drive configuration/)).toBeInTheDocument();
    });

    // onNext should not be called on error
    expect(onNext).not.toHaveBeenCalled();
  });
});
