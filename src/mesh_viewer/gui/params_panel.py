"""Editable form for meshing and uniforming (remeshing) parameters.

This is the UI surface for editing MeshingParams / UniformParams before a run.
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mesh_viewer.core.meshing import MeshingParams
from mesh_viewer.core.uniforming import UniformParams


class ParamsPanel(QWidget):
    """Two group boxes of spin boxes / fields bound to MeshingParams and UniformParams."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        mesh_box = QGroupBox("Meshing")
        mesh_form = QFormLayout(mesh_box)
        self.element_size = QDoubleSpinBox()
        self.element_size.setRange(0.001, 1e6)
        self.element_size.setValue(20.0)
        self.min_element_size = QDoubleSpinBox()
        self.min_element_size.setRange(0.0001, 1e6)
        self.min_element_size.setDecimals(4)
        self.min_element_size.setValue(0.2)
        self.prism_layers = QSpinBox()
        self.prism_layers.setRange(0, 100)
        self.prism_layers.setValue(5)
        self.prism_growth_rate = QDoubleSpinBox()
        self.prism_growth_rate.setRange(1.0, 3.0)
        self.prism_growth_rate.setSingleStep(0.05)
        self.prism_growth_rate.setValue(1.2)
        self.prism_surface_expression = QLineEdit("*")
        mesh_form.addRow("Element size (max)", self.element_size)
        mesh_form.addRow("Min element size", self.min_element_size)
        mesh_form.addRow("Prism layers", self.prism_layers)
        mesh_form.addRow("Prism growth rate", self.prism_growth_rate)
        mesh_form.addRow("Prism surface expression", self.prism_surface_expression)

        uniform_box = QGroupBox("Uniforming (remesh)")
        uniform_form = QFormLayout(uniform_box)
        self.target_len_mm = QDoubleSpinBox()
        self.target_len_mm.setRange(0.001, 1e6)
        self.target_len_mm.setValue(5.0)
        self.iterations = QSpinBox()
        self.iterations.setRange(1, 50)
        self.iterations.setValue(3)
        self.feature_deg = QDoubleSpinBox()
        self.feature_deg.setRange(0.0, 180.0)
        self.feature_deg.setValue(30.0)
        self.max_surf_dist_mm = QDoubleSpinBox()
        self.max_surf_dist_mm.setRange(0.0, 1e6)
        self.max_surf_dist_mm.setValue(0.1)
        self.check_surf_dist = QCheckBox("Cap reprojection distance")
        self.check_surf_dist.setChecked(True)
        uniform_form.addRow("Target edge length (mm)", self.target_len_mm)
        uniform_form.addRow("Iterations", self.iterations)
        uniform_form.addRow("Feature angle (deg)", self.feature_deg)
        uniform_form.addRow("Max surface distance (mm)", self.max_surf_dist_mm)
        uniform_form.addRow("", self.check_surf_dist)

        layout.addWidget(mesh_box)
        layout.addWidget(uniform_box)
        layout.addStretch(1)

    def get_meshing_params(self) -> MeshingParams:
        return MeshingParams(
            element_size=self.element_size.value(),
            min_element_size=self.min_element_size.value(),
            prism_layers=self.prism_layers.value(),
            prism_growth_rate=self.prism_growth_rate.value(),
            prism_surface_expression=self.prism_surface_expression.text() or "*",
        )

    def get_uniform_params(self) -> UniformParams:
        return UniformParams(
            target_len_mm=self.target_len_mm.value(),
            iterations=self.iterations.value(),
            feature_deg=self.feature_deg.value(),
            max_surf_dist_mm=self.max_surf_dist_mm.value(),
            check_surf_dist=self.check_surf_dist.isChecked(),
        )
