import { useRef, useState } from 'react';
import { importSong, getImportStatus } from '../api.js';

const POLL_INTERVAL_MS = 2000;

export function ImportSong({ onImportComplete }) {
  const [job, setJob] = useState(null); // { state, status_message, song_id }
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setError(null);

    try {
      const { job_id, song_id } = await importSong(file);
      setJob({ state: 'queued', status_message: 'Queued', song_id });
      pollStatus(job_id, song_id);
    } catch (err) {
      setError(err.message);
    }

    e.target.value = ''; // allow re-selecting the same file later
  };

  const pollStatus = (jobId, songId) => {
    pollRef.current = setInterval(async () => {
      try {
        const status = await getImportStatus(jobId);
        setJob({ ...status, song_id: songId });

        if (status.state === 'done') {
          clearInterval(pollRef.current);
          onImportComplete();
        } else if (status.state === 'error') {
          clearInterval(pollRef.current);
          setError(status.error);
        }
      } catch (err) {
        clearInterval(pollRef.current);
        setError(err.message);
      }
    }, POLL_INTERVAL_MS);
  };

  const isBusy = job && job.state !== 'done' && job.state !== 'error';

  return (
    <div className="import-song">
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        onChange={handleFileChange}
        disabled={isBusy}
        id="import-file-input"
        className="import-song__input"
      />
      <label htmlFor="import-file-input" className="import-song__label">
        {isBusy ? 'Processing\u2026' : '+ Import a song (runs locally, slow on CPU)'}
      </label>

      {job && (
        <div className="import-song__status">
          <span className="import-song__status-message">{job.status_message}</span>
          {isBusy && (
            <span className="import-song__warning">
              This can take 15\u201340 min on a CPU-only laptop. The Colab notebook does this
              in under a minute if you'd rather not wait.
            </span>
          )}
        </div>
      )}

      {error && <div className="import-song__error">Import failed: {error}</div>}
    </div>
  );
}
