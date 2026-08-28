"""Small dependency-free size based log rotation."""
from __future__ import annotations

from pathlib import Path


def rotate_if_needed(path: Path, incoming_bytes: int, *, max_bytes: int,
                     backup_count: int) -> None:
    """Rotate ``path`` before an append would cross ``max_bytes``.

    Rotation is best-effort: logging must never stop the assistant. ``.1`` is
    always the newest archive and archives beyond ``backup_count`` disappear.
    """
    if max_bytes <= 0 or backup_count <= 0 or not path.is_file():
        return
    try:
        if path.stat().st_size + max(0, incoming_bytes) <= max_bytes:
            return
        oldest = path.with_name(f"{path.name}.{backup_count}")
        oldest.unlink(missing_ok=True)
        for number in range(backup_count - 1, 0, -1):
            source = path.with_name(f"{path.name}.{number}")
            if source.exists():
                source.replace(path.with_name(f"{path.name}.{number + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
    except OSError:
        pass
