import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { SongDetail } from '../SongDetail.jsx';
import * as api from '../../../api.js';

vi.mock('../../../api.js', () => ({
  getManifest: vi.fn(),
}));

// Mock AudioEngine
const mockEngine = {
  setMute: vi.fn(),
  setSolo: vi.fn(),
  setVolume: vi.fn(),
  play: vi.fn(),
  pause: vi.fn(),
  getStemRMS: vi.fn(() => 0),
  duration: 120,
};

// Mock canvas
HTMLCanvasElement.prototype.getContext = () => null;

describe('SongDetail Component', () => {
  const fullManifest = {
    title: 'Test Song',
    bpm: 120,
    key: 'C Major',
    stems: ['vocals', 'drums'],
    has_lyrics: true,
    has_beats: true,
    notes_available: ['vocals']
  };

  const partialManifest = {
    title: 'No Meta Song',
    stems: ['vocals'],
    has_lyrics: false,
    has_beats: false,
    notes_available: []
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('T1: Mount with full manifest - Title, BPM, key rendered correctly', () => {
    render(<SongDetail songId="test-1" initialManifest={fullManifest} engine={mockEngine} onBack={() => {}} />);
    
    expect(screen.getByText('Test Song')).toBeInTheDocument();
    expect(screen.getByText('BPM: 120')).toBeInTheDocument();
    expect(screen.getByText('Key: C Major')).toBeInTheDocument();
    expect(screen.getByText('Vocals')).toBeInTheDocument();
    expect(screen.getByText('Drums')).toBeInTheDocument();
  });

  it('T2: Mount with manifest missing BPM/key - Those fields absent from DOM, no crash', () => {
    render(<SongDetail songId="test-2" initialManifest={partialManifest} engine={mockEngine} onBack={() => {}} />);
    
    expect(screen.getByText('No Meta Song')).toBeInTheDocument();
    expect(screen.queryByText(/BPM:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Key:/)).not.toBeInTheDocument();
  });

  it('T3: Mute button clicked on a stem - AudioEngine.setMute called with correct stem name and true', () => {
    render(<SongDetail songId="test-1" initialManifest={fullManifest} engine={mockEngine} onBack={() => {}} />);
    
    const muteButtons = screen.getAllByText('M');
    fireEvent.click(muteButtons[0]); // Click Mute on Vocals
    
    expect(mockEngine.setMute).toHaveBeenCalledWith('vocals', true);
  });

  it('T4: Solo button clicked - engine.setSolo called', () => {
    render(<SongDetail songId="test-1" initialManifest={fullManifest} engine={mockEngine} onBack={() => {}} />);
    
    const soloButtons = screen.getAllByText('S');
    fireEvent.click(soloButtons[0]); // Click Solo on Vocals
    
    expect(mockEngine.setSolo).toHaveBeenCalledWith('vocals', true);
  });

  it('T5: Volume fader changed - AudioEngine.setVolume called with new value', () => {
    render(<SongDetail songId="test-1" initialManifest={fullManifest} engine={mockEngine} onBack={() => {}} />);
    
    const sliders = screen.getAllByRole('slider');
    fireEvent.change(sliders[0], { target: { value: '0.75' } });
    
    expect(mockEngine.setVolume).toHaveBeenCalledWith('vocals', 0.75);
  });

  it('T6: Back arrow clicked - onBack prop called', () => {
    const onBackMock = vi.fn();
    render(<SongDetail songId="test-1" initialManifest={fullManifest} engine={mockEngine} onBack={onBackMock} />);
    
    fireEvent.click(screen.getByText('← Back'));
    expect(onBackMock).toHaveBeenCalled();
  });

  it('T7: loading: true state - Loading indicator visible, stem grid not rendered', async () => {
    // If we do not pass initialManifest, it will fetch it and set loading to true initially
    let resolvePromise;
    api.getManifest.mockReturnValue(new Promise(resolve => {
      resolvePromise = resolve;
    }));
    
    render(<SongDetail songId="test-3" engine={mockEngine} onBack={() => {}} />);
    
    expect(screen.getByText('Loading song details...')).toBeInTheDocument();
    expect(screen.queryByText('Vocals')).not.toBeInTheDocument();
    
    resolvePromise(fullManifest);
    
    await waitFor(() => {
      expect(screen.queryByText('Loading song details...')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Vocals')).toBeInTheDocument();
  });

  it('T8: Metadata pill for lyrics present', () => {
    render(<SongDetail songId="test-1" initialManifest={fullManifest} engine={mockEngine} onBack={() => {}} />);
    
    // We rendered "Lyrics Available"
    expect(screen.getByText('Lyrics Available')).toBeInTheDocument();
  });

  it('T9: Metadata pill for lyrics absent', () => {
    render(<SongDetail songId="test-2" initialManifest={partialManifest} engine={mockEngine} onBack={() => {}} />);
    
    // We rendered "Lyrics Unavailable"
    expect(screen.getByText('Lyrics Unavailable')).toBeInTheDocument();
  });
});
