"""Meshing wrapper around the existing ansys.meshing.prime pipeline (see meshing.py).

Adapts the standalone script into a single-component function interface that the
background pipeline worker can call per CAD file, with parameters that are all
editable from the UI's ParamsPanel (see gui/params_panel.py).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def find_prime_root() -> Optional[str]:
    """Locate an installed Ansys Prime Server root directory.

    ansys-meshing-prime's own auto-detection (get_ansys_prime_server_root) only
    recognizes one hardcoded Ansys version per client release, so it can miss
    an install that's actually present (e.g. client 0.10.4 only looks for
    AWP_ROOT261, even though v252/v241 are installed and perfectly usable).
    This scans all AWP_ROOT<version> environment variables instead and picks
    the highest version that has a meshing/Prime folder.
    """
    candidates = {}
    for name, root in os.environ.items():
        match = re.fullmatch(r"AWP_ROOT(\d+)", name)
        if not match or not root:
            continue
        prime_root = os.path.join(root, "meshing", "Prime")
        if os.path.isdir(prime_root):
            candidates[int(match.group(1))] = prime_root
    if not candidates:
        return None
    return candidates[max(candidates)]


def _format_num(value: float) -> str:
    """Format a number compactly for use in a folder name (e.g. 0.2 -> "0.2", 20.0 -> "20")."""
    return f"{value:g}"


@dataclass
class MeshingParams:
    """User-editable surface/volume meshing settings (mirrors meshing.py constants)."""

    element_size: float = 20.0
    min_element_size: float = 0.2
    prism_layers: int = 5
    prism_growth_rate: float = 1.2
    prism_surface_expression: str = "*"

    def params_tag(self) -> str:
        """Short folder-name tag encoding these settings, e.g. "es20_esmin02_p5_pg12".

        Used to keep output from different parameter choices in separate,
        identifiable subfolders instead of overwriting each other.
        """
        return (
            f"es{_format_num(self.element_size).replace('.', '')}"
            f"_esmin{_format_num(self.min_element_size).replace('.', '')}"
            f"_p{self.prism_layers}"
            f"_pg{_format_num(self.prism_growth_rate).replace('.', '')}"
        )


def mesh_component(input_path: Path, output_dir: Path, params: MeshingParams) -> list[Path]:
    """Mesh every part found in the CAD file at input_path and export one STL per part.

    Single Prime session (no multi-worker partitioning) - adapted from the
    import/scaffold/surface-mesh/volume-mesh/export sequence in meshing.py's
    _mesh_part(). Returns the list of exported STL paths.
    """
    from ansys.meshing import prime  # imported lazily: optional heavy dependency

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []

    prime_client = prime.launch_prime(timeout=120, prime_root=find_prime_root())
    try:
        model = prime_client.model
        file_io = prime.FileIO(model)
        if input_path.suffix.lower() == ".pmdat":
            file_io.read_pmdat(str(input_path), prime.FileReadParams(model=model))
        else:
            file_io.import_cad(
                file_name=str(input_path),
                params=prime.ImportCadParams(model=model, part_creation_type=prime.PartCreationType.BODY),
            )

        # Rename the imported part(s) to match the source file's own name rather
        # than whatever body/label name is embedded in the CAD data - so the
        # exported STL preserves the original input filename instead of an
        # internal CAD name that may differ from it.
        parts = list(model.parts)
        if len(parts) == 1:
            parts[0].set_suggested_name(input_path.stem)
        else:
            for i, part in enumerate(parts, start=1):
                part.set_suggested_name(f"{input_path.stem}_{i}")

        mesh_util = prime.lucid.Mesh(model=model)

        for part in model.parts:
            topo_faces = part.get_topo_faces()
            if not topo_faces:
                continue

            scaffold_params = prime.ScaffolderParams(
                model,
                absolute_dist_tol=0.1 * params.min_element_size,
                intersection_control_mask=prime.IntersectionMask.FACEFACEANDEDGEEDGE,
                constant_mesh_size=params.min_element_size,
            )
            prime.Scaffolder(model, part.id).scaffold_topo_faces_and_beams(
                topo_faces=topo_faces, topo_beams=[], params=scaffold_params
            )

            surface_scope = prime.lucid.SurfaceScope(
                part_expression=part.name,
                scope_evaluation_type=prime.ScopeEvaluationType.LABELS,
                entity_expression="*",
            )
            mesh_util.surface_mesh(
                min_size=params.min_element_size,
                max_size=params.element_size,
                generate_quads=False,
                scope=surface_scope,
            )

            volume_scope = prime.lucid.VolumeScope(
                part_expression=part.name,
                scope_evaluation_type=prime.ScopeEvaluationType.LABELS,
                entity_expression="*",
            )
            mesh_util.volume_mesh(
                volume_fill_type=prime.VolumeFillType.TET,
                prism_layers=params.prism_layers,
                prism_surface_expression=params.prism_surface_expression,
                growth_rate=params.prism_growth_rate,
                scope=volume_scope,
            )

            mesh_util.delete_topology(part_expression=part.name)

            safe_name = part.name.replace(" ", "_")
            stl_path = output_dir / f"{safe_name}.stl"
            file_io.export_stl(str(stl_path), prime.ExportSTLParams(model=model, part_ids=[part.id]))
            exported.append(stl_path)
    finally:
        prime_client.exit()

    return exported
