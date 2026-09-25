import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ImportDrive } from '../ImportDrive.jsx';
import * as api from '../../api.js';

vi.mock('../../api.js', () => ({
  ingestZip: vi.fn(),
}));

describe('ImportDrive', () => {
  const mockOnImportComplete = vi.fn();
  const defaultDriveConfig = { drivePath: '/mock/drive', mwtnFolder: 'mwtn' };

  beforeEach(() => {
    vi.clearAllMocks();
    window.electronAPI = {
      listFolder: vi.fn(),
      joinPath: vi.fn((...args) => args.join('/')),
    };
  });

  afterEach(() => {
    delete window.electronAPI;
  });

  it('T1: Drive folder has 0 ZIPs -> Shows "No new songs found"', async () => {
    window.electronAPI.listFolder.mockResolvedValue([]);
    render(<ImportDrive songs={[]} onImportComplete={mockOnImportComplete} driveConfig={defaultDriveConfig} />);
    
    await userEvent.click(screen.getByRole('button', { name: /Import from Drive/i }));
    
    await waitFor(() => {
      expect(screen.getByText('No new songs found')).toBeInTheDocument();
    });
    expect(api.ingestZip).not.toHaveBeenCalled();
  });

  it('T2: Drive folder has 2 ZIPs, both new -> Calls ingestZip twice, calls onImportComplete twice', async () => {
    window.electronAPI.listFolder.mockResolvedValue(['song1.zip', 'song2.zip']);
    api.ingestZip
      .mockResolvedValueOnce({ song_id: 'song1', title: 'Song 1' })
      .mockResolvedValueOnce({ song_id: 'song2', title: 'Song 2' });

    render(<ImportDrive songs={[]} onImportComplete={mockOnImportComplete} driveConfig={defaultDriveConfig} />);
    
    await userEvent.click(screen.getByRole('button', { name: /Import from Drive/i }));

    await waitFor(() => {
      expect(screen.getByText('Import complete — 2 new songs added')).toBeInTheDocument();
    });

    expect(api.ingestZip).toHaveBeenCalledTimes(2);
    expect(api.ingestZip).toHaveBeenNthCalledWith(1, '/mock/drive/mwtn/song1.zip');
    expect(api.ingestZip).toHaveBeenNthCalledWith(2, '/mock/drive/mwtn/song2.zip');
    expect(mockOnImportComplete).toHaveBeenCalledTimes(2);
  });

  it('T3: One ZIP already in song list -> Only calls ingest for the new one', async () => {
    window.electronAPI.listFolder.mockResolvedValue(['song1.zip', 'song2.zip']);
    api.ingestZip.mockResolvedValueOnce({ song_id: 'song2', title: 'Song 2' });

    const existingSongs = [{ song_id: 'song1', title: 'Song 1' }];
    render(<ImportDrive songs={existingSongs} onImportComplete={mockOnImportComplete} driveConfig={defaultDriveConfig} />);
    
    await userEvent.click(screen.getByRole('button', { name: /Import from Drive/i }));

    await waitFor(() => {
      expect(screen.getByText('Import complete — 1 new songs added')).toBeInTheDocument();
    });

    expect(api.ingestZip).toHaveBeenCalledTimes(1);
    expect(api.ingestZip).toHaveBeenCalledWith('/mock/drive/mwtn/song2.zip');
  });

  it('T4: One ingest fails mid-batch -> Continues to next ZIP, shows failure summary at end', async () => {
    window.electronAPI.listFolder.mockResolvedValue(['song1.zip', 'song2.zip', 'song3.zip']);
    api.ingestZip
      .mockResolvedValueOnce({ song_id: 'song1' })
      .mockRejectedValueOnce(new Error('Corrupt zip'))
      .mockResolvedValueOnce({ song_id: 'song3' });

    render(<ImportDrive songs={[]} onImportComplete={mockOnImportComplete} driveConfig={defaultDriveConfig} />);
    
    await userEvent.click(screen.getByRole('button', { name: /Import from Drive/i }));

    await waitFor(() => {
      expect(screen.getByText(/Import complete — 2 new songs added. Errors: song2.zip: Corrupt zip/i)).toBeInTheDocument();
    });

    expect(api.ingestZip).toHaveBeenCalledTimes(3);
    expect(mockOnImportComplete).toHaveBeenCalledTimes(2);
  });

  it('T5: Button disabled during import -> Assert button disabled attribute set while import running', async () => {
    let resolveList;
    const listPromise = new Promise(resolve => { resolveList = resolve; });
    window.electronAPI.listFolder.mockReturnValue(listPromise);

    render(<ImportDrive songs={[]} onImportComplete={mockOnImportComplete} driveConfig={defaultDriveConfig} />);
    const button = screen.getByRole('button', { name: /Import from Drive/i });
    
    expect(button).not.toBeDisabled();
    await userEvent.click(button);
    
    expect(button).toBeDisabled();

    resolveList([]);
    
    await waitFor(() => {
      expect(screen.getByText('No new songs found')).toBeInTheDocument();
    });
    expect(button).not.toBeDisabled();
  });

  it('T6: listFolder IPC absent (browser) -> Button renders but shows "Desktop only" tooltip, click is no-op', async () => {
    delete window.electronAPI;
    
    render(<ImportDrive songs={[]} onImportComplete={mockOnImportComplete} driveConfig={defaultDriveConfig} />);
    const button = screen.getByRole('button', { name: /Import from Drive/i });
    
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Desktop only');
    
    await userEvent.click(button);
    expect(api.ingestZip).not.toHaveBeenCalled();
  });
});
