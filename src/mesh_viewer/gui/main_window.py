"""Main application window: ties together the component tree, viewer tabs, params, and log panel."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mesh_viewer.core.pipeline import PipelineWorker
from mesh_viewer.gui.component_tree import ComponentTree
from mesh_viewer.gui.log_panel import LogPanel
from mesh_viewer.gui.params_panel import ParamsPanel
from mesh_viewer.gui.viewer_panel import ViewerPanel
from mesh_viewer.io.discovery import discover_components, discover_meshes
from mesh_viewer.resources import ICON_PATH


class MainWindow(QMainWindow):
    """Import/output path fields, component tree, viewer tabs, editable params, and log panel."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mesh Viewer")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1300, 850)

        self._worker: PipelineWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)

        paths_row = QHBoxLayout()
        self.input_label = QLabel("Input:")
        self.input_path_edit = QLineEdit()
        self.input_browse_button = QPushButton("Browse input...")
        self.input_browse_button.clicked.connect(self._browse_input)
        self.output_path_edit = QLineEdit()
        output_browse = QPushButton("Browse output...")
        output_browse.clicked.connect(self._browse_output)
        paths_row.addWidget(self.input_label)
        paths_row.addWidget(self.input_path_edit)
        paths_row.addWidget(self.input_browse_button)
        paths_row.addWidget(QLabel("Output:"))
        paths_row.addWidget(self.output_path_edit)
        paths_row.addWidget(output_browse)
        central_layout.addLayout(paths_row)

        controls_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Mesh + Uniform", "full")
        self.mode_combo.addItem("Mesh only", "mesh_only")
        self.mode_combo.addItem("Uniform only (re-uniform tree selection)", "uniform_only")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        controls_row.addWidget(QLabel("Mode:"))
        controls_row.addWidget(self.mode_combo)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._on_start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        controls_row.addWidget(self.start_button)
        controls_row.addWidget(self.stop_button)
        controls_row.addStretch(1)
        # Independent of the meshing pipeline: just browse to a folder of
        # already-produced mesh files and load them straight into the tree/viewer.
        self.load_output_button = QPushButton("Load Output Folder...")
        self.load_output_button.clicked.connect(self._on_load_output_folder)
        controls_row.addWidget(self.load_output_button)
        central_layout.addLayout(controls_row)

        # A single viewer that can hold several meshes at once (see
        # ViewerPanel.set_meshes) - kept in sync with the component tree's
        # (multi-)selection, so ctrl/shift-click lets you compare parts side
        # by side in the same 3D scene.
        self.viewer = ViewerPanel()
        self.viewer.screenshot_copied.connect(self._on_screenshot_copied)
        central_layout.addWidget(self.viewer)

        self.component_tree = ComponentTree()
        self.component_tree.component_selected.connect(self._on_components_selected)
        tree_dock = QDockWidget("Components", self)
        tree_dock.setWidget(self.component_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tree_dock)

        self.params_panel = ParamsPanel()
        self.params_panel.max_surf_dist_preview_changed.connect(self.viewer.set_offset_preview)
        params_dock = QDockWidget("Parameters", self)
        params_dock.setWidget(self.params_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, params_dock)

        self.log_panel = LogPanel()
        log_dock = QDockWidget("Log", self)
        log_dock.setWidget(self.log_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)

        self._on_mode_changed()

    def _on_mode_changed(self) -> None:
        """Uniform-only re-uniforms whatever's checked in the Components tree
        (i.e. currently shown in the viewer), so the separate Input folder
        picker doesn't apply and is disabled to avoid confusion.
        """
        is_uniform_only = self.mode_combo.currentData() == "uniform_only"
        self.input_label.setEnabled(not is_uniform_only)
        self.input_path_edit.setEnabled(not is_uniform_only)
        self.input_browse_button.setEnabled(not is_uniform_only)
        if is_uniform_only:
            self.input_path_edit.setPlaceholderText("(uses the Components tree's checked items)")
        else:
            self.input_path_edit.setPlaceholderText("")

    def _browse_input(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select input folder")
        if path:
            self.input_path_edit.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self.output_path_edit.setText(path)

    def _on_load_output_folder(self) -> None:
        """Open an existing folder of mesh files directly, without running the pipeline."""
        path = QFileDialog.getExistingDirectory(self, "Select folder of existing mesh files")
        if not path:
            return
        try:
            meshes = discover_meshes(Path(path))
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            self.log_panel.append_message("error", str(exc))
            return
        self.component_tree.set_outputs(meshes, root=Path(path))
        self.log_panel.append_message("info", f"Loaded {len(meshes)} existing mesh file(s) from {path}")

    def _on_start(self) -> None:
        output_path = Path(self.output_path_edit.text())
        mode = self.mode_combo.currentData()

        if mode == "uniform_only":
            # Re-uniform whatever mesh(es) are currently checked in the
            # Components tree (i.e. shown in the viewer) - handy for tuning
            # remeshing parameters while looking right at the part.
            checked = self.component_tree.checked_output_paths()
            if not checked:
                self.log_panel.append_message(
                    "error", "Check one or more meshed parts in the Components tree to re-uniform."
                )
                return
            components = [Path(p) for p in checked]
        else:
            try:
                input_path = Path(self.input_path_edit.text())
                components = discover_components(input_path)
            except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
                self.log_panel.append_message("error", str(exc))
                return
            self.component_tree.set_components(components)

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        # Parameters are read fresh from the UI at run start, so any edits made
        # in ParamsPanel before clicking Start are what get used.
        self._worker = PipelineWorker(
            components,
            output_path,
            self.params_panel.get_meshing_params(),
            self.params_panel.get_uniform_params(),
            mode=mode,
        )
        self._worker.status_changed.connect(self.component_tree.set_status)
        self._worker.log_message.connect(self.log_panel.append_message)
        self._worker.component_done.connect(self._on_component_done)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()

    def _on_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.log_panel.append_message("info", "Pipeline finished.")

    def _on_component_done(self, component_path: str, stage: str, output_path: str) -> None:
        self.component_tree.add_output(component_path, stage, output_path)
        self.log_panel.append_message("info", f"{stage}: {component_path} -> {output_path}")

    def _on_screenshot_copied(self, success: bool, message: str) -> None:
        self.log_panel.append_message("info" if success else "error", message)

    def _on_components_selected(self, entries: list[tuple[str, float]]) -> None:
        valid_entries = []
        for output_path, scale in entries:
            path = Path(output_path)
            if path.exists():
                valid_entries.append((path, scale))
            else:
                self.log_panel.append_message("error", f"Mesh file not found: {path}")
        self.viewer.set_meshes(valid_entries)

