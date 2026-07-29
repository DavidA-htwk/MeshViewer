"""Uniforming wrapper around the existing pymeshlab isotropic remeshing (see uniform_mesh.py).

Adapts the standalone script into a single-component function interface that the
background pipeline worker can call per meshed part, with parameters that are all
editable from the UI's ParamsPanel (see gui/params_panel.py).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class UniformParams:
    """User-editable isotropic remeshing settings (mirrors uniform_mesh.py CLI args)."""

    target_len_mm: float = 5.0
    iterations: int = 3
    feature_deg: float = 30.0
    max_surf_dist_mm: Optional[float] = None  # falls back to target_len_mm if None
    check_surf_dist: bool = True

    def params_tag(self) -> str:
        """Short folder-name tag encoding these settings, e.g. "tl5_it3_fd30_msd01".

        Used to keep output from different parameter choices in separate,
        identifiable subfolders instead of overwriting each other.
        """
        max_surf_dist_mm = self.max_surf_dist_mm if self.max_surf_dist_mm is not None else self.target_len_mm
        return (
            f"tl{f'{self.target_len_mm:g}'.replace('.', '')}"
            f"_it{self.iterations}"
            f"_fd{f'{self.feature_deg:g}'.replace('.', '')}"
            f"_msd{f'{max_surf_dist_mm:g}'.replace('.', '')}"
        )


def uniform_component(src_path: Path, dst_path: Path, params: UniformParams) -> Path:
    """Apply isotropic explicit remeshing to the mesh at src_path, writing dst_path.

    Adapted from remesh_file() in uniform_mesh.py.
    """
    import pymeshlab  # imported lazily: optional heavy dependency

    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(src_path))

    max_surf_dist_mm = params.max_surf_dist_mm if params.max_surf_dist_mm is not None else params.target_len_mm

    ms.meshing_isotropic_explicit_remeshing(
        iterations=params.iterations,
        targetlen=pymeshlab.PureValue(params.target_len_mm),
        adaptive=False,
        featuredeg=params.feature_deg,
        checksurfdist=params.check_surf_dist,
        maxsurfdist=pymeshlab.PureValue(max_surf_dist_mm),
    )

    dst_path = Path(dst_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    ms.save_current_mesh(str(dst_path))
    return dst_path
