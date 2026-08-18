export function SongSelector({ songs, selectedSongId, onSelect, onDelete }) {
  if (songs.length === 0) {
    return (
      <div className="song-selector song-selector--empty">
        <p>No songs yet. Import one below, or process one via the Colab notebook and drop it into backend/data/.</p>
      </div>
    );
  }

  return (
    <div className="song-selector">
      {songs.map((song) => (
        <div
          key={song.song_id}
          className={`song-selector__item ${song.song_id === selectedSongId ? 'is-selected' : ''}`}
        >
          <button className="song-selector__name" onClick={() => onSelect(song.song_id)}>
            {song.song_id.replace(/_/g, ' ')}
          </button>
          <button
            className="song-selector__delete"
            onClick={() => onDelete(song.song_id)}
            aria-label={`Delete ${song.song_id}`}
            title="Delete"
          >
            \u00D7
          </button>
        </div>
      ))}
    </div>
  );
}
