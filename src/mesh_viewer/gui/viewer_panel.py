"""3D viewer panel: embeds a pyvistaqt QtInteractor showing one or more meshes at once."""

from itertools import cycle
from pathlib import Path

import pyvista as pv
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QGuiApplication, QImage
from PySide6.QtWidgets import QLabel, QToolBar, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

# Cycled across simultaneously loaded meshes so overlapping parts stay visually
# distinguishable in the same scene.
_COLOR_PALETTE = [
    "tan",
    "lightblue",
    "lightgreen",
    "salmon",
    "plum",
    "khaki",
    "lightcoral",
    "paleturquoise",
]

# Colors/style for the max-surf-dist offset preview shells - fixed and distinct
# from the mesh color palette so the tolerance band reads the same way
# regardless of which mesh(es) it's shown around. Rendered as dashed wireframe
# lines (rather than a solid translucent surface) so the underlying mesh stays
# clearly visible through the gaps.
_OFFSET_OUTWARD_COLOR = "lightgreen"
_OFFSET_INWARD_COLOR = "deepskyblue"
_OFFSET_OPACITY = 0.8
_OFFSET_LINE_WIDTH = 2.0
_OFFSET_STIPPLE_PATTERN = 0xF0F0  # alternating on/off bits -> dashed, gapped lines
_OFFSET_STIPPLE_REPEAT = 2


class ViewerPanel(QWidget):
    """A single 3D scene that can display several meshes side by side at once.

    Call set_meshes() with the full list of (path, scale) entries that should
    currently be visible - meshes no longer in the list are removed and new
    ones are added, so it stays in sync with e.g. the component tree's
    checked items and their per-folder scale factors.
    """

    screenshot_copied = Signal(bool, str)  # success, message

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        toolbar = QToolBar()
        self._wireframe_action = QAction("Wireframe", self, checkable=True)
        self._wireframe_action.toggled.connect(self._on_style_changed)
        self._edges_action = QAction("Show Edges", self, checkable=True)
        self._edges_action.toggled.connect(self._on_style_changed)
        reset_action = QAction("Reset Camera", self)
        reset_action.triggered.connect(self.reset_camera)
        screenshot_action = QAction("Copy Screenshot", self)
        screenshot_action.triggered.connect(self.copy_screenshot_to_clipboard)
        toolbar.addAction(self._wireframe_action)
        toolbar.addAction(self._edges_action)
        toolbar.addAction(reset_action)
        toolbar.addAction(screenshot_action)
        layout.addWidget(toolbar)

        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)

        self._stats_label = QLabel("No mesh loaded")
        layout.addWidget(self._stats_label)

        self._meshes: dict[str, pv.PolyData] = {}
        self._scales: dict[str, float] = {}
        self._actors: dict[str, object] = {}
        self._colors: dict[str, str] = {}
        self._color_cycle = cycle(_COLOR_PALETTE)
        self._has_loaded_once = False

        self._offset_actors: dict[str, object] = {}
        self._offset_preview_enabled = False
        self._offset_preview_distance = 0.0

    def set_meshes(self, entries: list[tuple[Path, float]]) -> None:
        """Show exactly these (path, scale) entries, loading new ones and dropping
        deselected ones. Re-checking an already-loaded mesh with a new scale
        just re-renders it scaled, without re-reading the file from disk.

        The camera is only auto-framed the first time this viewer ever loads a
        mesh; afterwards it's left exactly as the user has it, so adding/
        removing meshes, rescaling, or toggling wireframe/edges never yanks the
        view around. Use Reset Camera to reframe explicitly.
        """
        wanted = {str(p): scale for p, scale in entries}

        for key in list(self._meshes.keys()):
            if key not in wanted:
                self._meshes.pop(key, None)
                self._colors.pop(key, None)
                self._scales.pop(key, None)

        for key, scale in wanted.items():
            if key not in self._meshes:
                self._meshes[key] = pv.read(key)
                self._colors[key] = next(self._color_cycle)
            self._scales[key] = scale

        self._refresh_actors()

        if not self._has_loaded_once and self._meshes:
            self.plotter.reset_camera()
            self._has_loaded_once = True
        else:
            self.plotter.render()
        self._update_stats_label()

    def toggle_wireframe(self) -> None:
        self._wireframe_action.toggle()

    def toggle_edges(self) -> None:
        """Toggle drawing the meshes' triangle edges on top of their surface/wireframe."""
        self._edges_action.toggle()

    def set_offset_preview(self, enabled: bool, distance_mm: float) -> None:
        """Toggle the max-surf-dist live preview.

        When enabled, each shown mesh gets two translucent offset shells,
        displaced +/- distance_mm along its surface normals - the band within
        which uniforming's reprojection is allowed to move a vertex off the
        original surface (see UniformParams.max_surf_dist_mm).
        """
        self._offset_preview_enabled = enabled
        self._offset_preview_distance = distance_mm
        if self._meshes:
            self._refresh_actors()
            self.plotter.render()

    def _refresh_actors(self) -> None:
        for actor in self._actors.values():
            self.plotter.remove_actor(actor)
        self._actors.clear()
        for actor in self._offset_actors.values():
            self.plotter.remove_actor(actor)
        self._offset_actors.clear()

        style = "wireframe" if self._wireframe_action.isChecked() else "surface"
        show_edges = self._edges_action.isChecked()
        for key, mesh in self._meshes.items():
            scale = self._scales.get(key, 1.0)
            scaled_mesh = mesh if scale == 1.0 else mesh.copy()
            if scale != 1.0:
                scaled_mesh.points = scaled_mesh.points * scale
            # reset_camera=False is required here: pyvista's add_mesh() otherwise
            # auto-resets the camera itself whenever camera_set is False (which
            # it stays, since our own reset_camera() call doesn't flip that
            # flag) - without this, every wireframe/edges toggle or mesh
            # add/remove would silently reframe the view.
            self._actors[key] = self.plotter.add_mesh(
                scaled_mesh,
                style=style,
                show_edges=show_edges,
                color=self._colors[key],
                reset_camera=False,
            )

            if self._offset_preview_enabled and self._offset_preview_distance > 0:
                self._add_offset_preview_actors(key, scaled_mesh, self._offset_preview_distance * scale)

    def _add_offset_preview_actors(self, key: str, mesh: pv.PolyData, distance: float) -> None:
        """Best-effort: skip the preview for a mesh rather than fail the whole render."""
        try:
            normals_mesh = mesh.compute_normals(
                point_normals=True, cell_normals=False, auto_orient_normals=True, consistent_normals=True
            )
            outward = normals_mesh.warp_by_vector("Normals", factor=distance)
            inward = normals_mesh.warp_by_vector("Normals", factor=-distance)
        except Exception:
            return
        self._offset_actors[f"{key}::out"] = self._add_offset_shell(outward, _OFFSET_OUTWARD_COLOR)
        self._offset_actors[f"{key}::in"] = self._add_offset_shell(inward, _OFFSET_INWARD_COLOR)

    def _add_offset_shell(self, mesh: pv.PolyData, color: str):
        """Add one offset shell as dashed (gapped) wireframe lines rather than a
        solid translucent fill, so the underlying mesh remains easy to see.
        """
        actor = self.plotter.add_mesh(
            mesh,
            style="wireframe",
            color=color,
            opacity=_OFFSET_OPACITY,
            line_width=_OFFSET_LINE_WIDTH,
            reset_camera=False,
        )
        try:
            prop = actor.GetProperty()
            prop.SetLineStipplePattern(_OFFSET_STIPPLE_PATTERN)
            prop.SetLineStippleRepeatFactor(_OFFSET_STIPPLE_REPEAT)
        except AttributeError:
            pass  # stippling unsupported on this VTK build - plain dashed-less wireframe is still an improvement
        return actor

    def _on_style_changed(self, _checked: bool) -> None:
        if self._meshes:
            self._refresh_actors()
            self.plotter.render()

    def _update_stats_label(self) -> None:
        if not self._meshes:
            self._stats_label.setText("No mesh loaded")
            return
        total_points = sum(mesh.n_points for mesh in self._meshes.values())
        total_cells = sum(mesh.n_cells for mesh in self._meshes.values())
        self._stats_label.setText(
            f"{len(self._meshes)} mesh(es)  |  Vertices: {total_points}  |  Faces: {total_cells}"
        )

    def reset_camera(self) -> None:
        self.plotter.reset_camera()

    def copy_screenshot_to_clipboard(self) -> None:
        """Render the current scene and copy it to the system clipboard as an image."""
        try:
            image = self.plotter.screenshot(return_img=True)
            height, width, channels = image.shape
            fmt = QImage.Format.Format_RGB888 if channels == 3 else QImage.Format.Format_RGBA8888
            # .copy() detaches the QImage from the numpy buffer, which is not
            # guaranteed to stay alive/unchanged after this method returns.
            qimage = QImage(image.data, width, height, channels * width, fmt).copy()
            QGuiApplication.clipboard().setImage(qimage)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the viewer
            self.screenshot_copied.emit(False, str(exc))
        else:
            self.screenshot_copied.emit(True, "Screenshot copied to clipboard.")
