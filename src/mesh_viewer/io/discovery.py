"""Discover input CAD files and existing output mesh files under a given root path."""

from pathlib import Path

SUPPORTED_CAD_EXTS = {".step", ".stp", ".fmd"}
SUPPORTED_MESH_EXTS = {".stl", ".obj", ".ply", ".off"}


def discover_components(root_dir: Path) -> list[Path]:
    """Return the CAD files to queue for processing under root_dir.

    root_dir may be a single CAD file or a folder containing one or more
    supported CAD files (non-recursive). Raises FileNotFoundError/ValueError
    on bad input so the GUI can report it instead of crashing.
    """
    root_dir = Path(root_dir)
    if not root_dir.exists():
        raise FileNotFoundError(f"Path does not exist: {root_dir}")

    if root_dir.is_file():
        if root_dir.suffix.lower() not in SUPPORTED_CAD_EXTS:
            raise ValueError(f"Unsupported file type: {root_dir.suffix}")
        return [root_dir]

    if not root_dir.is_dir():
        raise NotADirectoryError(f"Not a file or directory: {root_dir}")

    components = sorted(p for p in root_dir.iterdir() if p.suffix.lower() in SUPPORTED_CAD_EXTS)
    if not components:
        raise FileNotFoundError(
            f"No CAD files ({', '.join(sorted(SUPPORTED_CAD_EXTS))}) found in {root_dir}"
        )
    return components


def discover_meshes(root_dir: Path) -> list[Path]:
    """Return already-produced mesh files found under root_dir (searched recursively).

    Lets the GUI open a folder of existing outputs directly in the viewer,
    independent of running the meshing/uniforming pipeline. Raises
    FileNotFoundError/ValueError on bad input so the GUI can report it instead
    of crashing.
    """
    root_dir = Path(root_dir)
    if not root_dir.exists():
        raise FileNotFoundError(f"Path does not exist: {root_dir}")

    if root_dir.is_file():
        if root_dir.suffix.lower() not in SUPPORTED_MESH_EXTS:
            raise ValueError(f"Unsupported mesh file type: {root_dir.suffix}")
        return [root_dir]

    if not root_dir.is_dir():
        raise NotADirectoryError(f"Not a file or directory: {root_dir}")

    meshes = sorted(p for p in root_dir.rglob("*") if p.suffix.lower() in SUPPORTED_MESH_EXTS)
    if not meshes:
        raise FileNotFoundError(
            f"No mesh files ({', '.join(sorted(SUPPORTED_MESH_EXTS))}) found in {root_dir}"
        )
    return meshes

