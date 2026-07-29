"""Resolve and prepare output paths, mirroring the source folder structure."""

from pathlib import Path


def resolve_output_path(source_path: Path, input_root: Path, output_root: Path, suffix: str = ".stl") -> Path:
    """Map a source CAD file path to its mirrored output path under output_root."""
    source_path = Path(source_path)
    input_root = Path(input_root)
    output_root = Path(output_root)
    try:
        rel = source_path.relative_to(input_root)
    except ValueError:
        rel = Path(source_path.name)
    return (output_root / rel).with_suffix(suffix)


def prepare_output_path(dst_path: Path, overwrite: bool = True) -> Path:
    """Ensure dst_path's parent exists and, unless overwrite, that it doesn't already exist."""
    dst_path = Path(dst_path)
    if dst_path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {dst_path}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    return dst_path
