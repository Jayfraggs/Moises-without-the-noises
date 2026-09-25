import React, { useState } from 'react';
import { ingestZip } from '../api.js';

export function ImportDrive({ songs, onImportComplete, driveConfig }) {
  const [isScanning, setIsScanning] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');

  const handleImport = async () => {
    if (!window.electronAPI) {
      setStatusMessage('Error: Not in Electron context');
      return;
    }

    if (!driveConfig || !driveConfig.drivePath || !driveConfig.mwtnFolder) {
      setStatusMessage('Error: Drive config not set. Check settings.');
      return;
    }

    setIsScanning(true);
    setStatusMessage('Scanning Drive folder...');

    try {
      const folderPath = await window.electronAPI.joinPath(driveConfig.drivePath, driveConfig.mwtnFolder);
      const files = await window.electronAPI.listFolder(folderPath);
      const zipFiles = files.filter(f => f.toLowerCase().endsWith('.zip'));

      if (zipFiles.length === 0) {
        setStatusMessage('No new songs found');
        return;
      }

      // Compare against existing songs list (which is a list of manifests)
      // Usually the song_id is the base name of the zip file
      const newZips = zipFiles.filter(zipName => {
        const potentialSongId = zipName.replace(/\.zip$/i, '');
        return !songs.some(s => s.song_id === potentialSongId || s.title === potentialSongId);
      });

      if (newZips.length === 0) {
        setStatusMessage('No new songs found');
        return;
      }

      let successCount = 0;
      let errors = [];

      for (let i = 0; i < newZips.length; i++) {
        const zipName = newZips[i];
        setStatusMessage(`Importing ${zipName} (${i + 1}/${newZips.length})...`);
        try {
          const fullZipPath = await window.electronAPI.joinPath(folderPath, zipName);
          const manifest = await ingestZip(fullZipPath);
          onImportComplete(manifest.song_id, manifest);
          successCount++;
        } catch (err) {
          console.error(`Failed to ingest ${zipName}:`, err);
          errors.push(`${zipName}: ${err.message}`);
        }
      }

      if (errors.length > 0) {
        setStatusMessage(`Import complete — ${successCount} new songs added. Errors: ${errors.join(', ')}`);
      } else {
        setStatusMessage(`Import complete — ${successCount} new songs added`);
      }
    } catch (err) {
      console.error('Scan failed:', err);
      setStatusMessage(`Scan failed: ${err.message}`);
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <div className="import-drive" style={{ padding: '0 16px 16px' }}>
      <button 
        className="btn btn-primary" 
        onClick={handleImport} 
        disabled={isScanning || !driveConfig || !driveConfig.drivePath || !window.electronAPI}
        title={!window.electronAPI ? "Desktop only" : ""}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
      >
        <span>⬇</span> Import from Drive
      </button>
      {statusMessage && (
        <div style={{ marginTop: '8px', fontSize: '0.85em', color: 'var(--text-secondary)' }}>
          {statusMessage}
        </div>
      )}
    </div>
  );
}
