"""Background pipeline orchestration: queues components through mesh -> uniform -> export.

Runs off the GUI thread as a QThread and reports per-component progress via Qt
signals so the GUI's ComponentTree and LogPanel can update live.
"""

from pathlib import Path
from typing import Literal

from PySide6.QtCore import QThread, Signal

from mesh_viewer.core.meshing import MeshingParams, mesh_component
from mesh_viewer.core.uniforming import UniformParams, uniform_component

# Mesh + uniform outputs are kept in separate, clearly-named subfolders so both
# versions of a part can be inspected/compared side by side in the viewer.
MESHED_SUBDIR = "meshed"
UNIFORMED_SUBDIR = "uniformed"

PipelineMode = Literal["full", "mesh_only", "uniform_only"]


class PipelineWorker(QThread):
    """Processes a queue of components through the meshing/uniforming pipeline.

    mode controls which stage(s) run:
      - "full": mesh then uniform every component (two separate output stages).
      - "mesh_only": mesh every component, skip uniforming.
      - "uniform_only": skip meshing - components are already-meshed STL files
        (e.g. from a previous mesh_only run) that get re-uniformed. Useful for
        iterating on remeshing parameters without re-running the expensive
        CAD meshing step each time.

    Emits status updates (meshing/uniforming/done/error) per component so the
    GUI can update live. Catches per-component exceptions so one failure does
    not abort the rest of the batch.
    """

    status_changed = Signal(str, str)  # component path, status
    log_message = Signal(str, str)  # level, message
    component_done = Signal(str, str, str)  # component path, stage ("meshed"/"uniformed"), output path
    finished_all = Signal()

    def __init__(
        self,
        components: list[Path],
        output_dir: Path,
        meshing_params: MeshingParams,
        uniform_params: UniformParams,
        mode: PipelineMode = "full",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.components = list(components)
        self.output_dir = Path(output_dir)
        self.meshing_params = meshing_params
        self.uniform_params = uniform_params
        self.mode = mode
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        """Process the queue sequentially, catching and reporting per-component errors."""
        # Output is nested under a tag encoding the chosen parameters (see
        # MeshingParams.params_tag / UniformParams.params_tag), so different
        # parameter choices land in separate, comparable subfolders instead of
        # overwriting each other:
        #   <output>/meshed/<mesh_tag>/<part>.stl
        #   <output>/uniformed/<mesh_tag>/<uniform_tag>/<part>.stl
        mesh_tag = self.meshing_params.params_tag()
        uniform_tag = self.uniform_params.params_tag()
        meshed_dir = self.output_dir / MESHED_SUBDIR / mesh_tag

        for component in self.components:
            if self._stop_requested:
                self.log_message.emit("info", "Stop requested - halting pipeline.")
                break

            component_key = str(component)
            try:
                if self.mode == "uniform_only":
                    # component is already a meshed STL living under
                    # meshed/<source_mesh_tag>/ - reuse that tag so the
                    # uniformed result stays traceable to its source mesh.
                    source_mesh_tag = component.parent.name
                    uniformed_dir = self.output_dir / UNIFORMED_SUBDIR / source_mesh_tag / uniform_tag
                    self.status_changed.emit(component_key, "uniforming")
                    final_path = uniformed_dir / component.name
                    uniform_component(component, final_path, self.uniform_params)
                    self.component_done.emit(component_key, "uniformed", str(final_path))
                else:
                    self.status_changed.emit(component_key, "meshing")
                    meshed_stl_paths = mesh_component(component, meshed_dir, self.meshing_params)
                    for meshed_stl in meshed_stl_paths:
                        self.component_done.emit(component_key, "meshed", str(meshed_stl))

                    if self.mode == "full":
                        uniformed_dir = self.output_dir / UNIFORMED_SUBDIR / mesh_tag / uniform_tag
                        for meshed_stl in meshed_stl_paths:
                            self.status_changed.emit(component_key, "uniforming")
                            final_path = uniformed_dir / meshed_stl.name
                            uniform_component(meshed_stl, final_path, self.uniform_params)
                            self.component_done.emit(component_key, "uniformed", str(final_path))

                self.status_changed.emit(component_key, "done")
            except Exception as exc:  # noqa: BLE001 - report and continue the batch
                self.status_changed.emit(component_key, "error")
                self.log_message.emit("error", f"{component.name}: {exc}")

        self.finished_all.emit()

