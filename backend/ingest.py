import json
from pathlib import Path, PurePosixPath
import zipfile


def ingest_zip(zip_path: str, data_dir: str) -> dict:
    """Validate a processed song ZIP, extract it into data_dir, and return the manifest."""
    zip_file = Path(zip_path)
    if not zip_file.is_file():
        raise ValueError(f"ZIP file does not exist: {zip_path}")

    data_root = Path(data_dir)
    data_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file, "r") as archive:
            normalized_names = []
            for name in archive.namelist():
                cleaned = name.replace("\\", "/").strip("/")
                if not cleaned:
                    continue
                parts = PurePosixPath(cleaned).parts
                if not parts or any(part in ("", ".", "..") for part in parts):
                    raise ValueError(f"ZIP contains an unsafe path: {name}")
                normalized_names.append(cleaned)

            if not normalized_names:
                raise ValueError("ZIP archive is empty")

            top_levels = {PurePosixPath(name).parts[0] for name in normalized_names}
            if len(top_levels) != 1:
                raise ValueError("ZIP must contain exactly one top-level directory")

            song_id = next(iter(top_levels))
            manifest_rel = f"{song_id}/manifest.json"
            if manifest_rel not in normalized_names:
                raise ValueError(f"ZIP must contain manifest.json inside '{song_id}/'")

            song_dir = data_root / song_id
            if (song_dir / "manifest.json").exists():
                manifest_path = song_dir / "manifest.json"
                try:
                    return json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Existing manifest.json in '{song_id}' is not valid JSON") from exc

            for info in archive.infolist():
                member_name = info.filename.replace("\\", "/").strip("/")
                if not member_name:
                    continue

                parts = PurePosixPath(member_name).parts
                if not parts or any(part in ("", ".", "..") for part in parts):
                    raise ValueError(f"ZIP contains an unsafe path: {info.filename}")

                if not parts[0] == song_id:
                    raise ValueError("ZIP must contain exactly one top-level directory")

                target_path = data_root.joinpath(*parts)
                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as src, target_path.open("wb") as dst:
                    dst.write(src.read())

            manifest_path = song_dir / "manifest.json"
            if not manifest_path.exists():
                raise ValueError(f"ZIP does not contain manifest.json inside '{song_id}/'")

            try:
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"manifest.json in '{song_id}' is not valid JSON") from exc

    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid ZIP file: {zip_path}") from exc
