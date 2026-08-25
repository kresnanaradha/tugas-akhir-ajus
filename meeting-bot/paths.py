from pathlib import Path


def sibling_path(recording_path: str, subfolder: str, suffix: str) -> Path:
    """Path for a same-meeting file in a sibling type folder next to videos/,
    e.g. recordings/videos/Foo_123.webm -> recordings/transcripts/Foo_123.txt"""
    base_dir = Path(recording_path).parent.parent
    path = base_dir / subfolder / (Path(recording_path).stem + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
