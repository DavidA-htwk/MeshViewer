"""Component tree widget: mirrors the discovered input files with per-item status.

Each input file may yield several meshed/uniformed output parts (STLs), so those
are added as selectable child nodes once the pipeline reports them done.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

_INPUT_PATH_ROLE = Qt.ItemDataRole.UserRole
_OUTPUT_PATH_ROLE = Qt.ItemDataRole.UserRole + 1
_STAGE_ROLE = Qt.ItemDataRole.UserRole + 2

# Names of the stage subfolders written by PipelineWorker (see core/pipeline.py).
# Duplicated here (rather than imported) to keep this widget decoupled from the
# pipeline module; only used to decide how much of an output path's parent
# folder chain is a meaningful "parameter tag" to show in labels.
_STAGE_SUBDIR_NAMES = ("meshed", "uniformed")


def _tag_label(output_path: Path) -> str:
    """Best-effort parameter-tag label derived from output_path's parent folder(s).

    meshed/<mesh_tag>/file.stl -> "<mesh_tag>"
    uniformed/<mesh_tag>/<uniform_tag>/file.stl -> "<mesh_tag>/<uniform_tag>"
    """
    parent = output_path.parent
    grandparent = parent.parent
    if grandparent.name in _STAGE_SUBDIR_NAMES:
        return parent.name
    return f"{grandparent.name}/{parent.name}"


class ComponentTree(QTreeWidget):
    """Tree of components with a status column (pending/meshing/uniforming/done/error).

    Supports multi-selection (ctrl/shift+click): emits component_selected with
    the full list of currently-selected output paths, so the viewer panel can
    show several meshes at once, in sync with the selection.
    """

    component_selected = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Component", "Status"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._items: dict[str, QTreeWidgetItem] = {}
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def set_components(self, paths: list[Path]) -> None:
        """Rebuild the tree from a fresh list of component paths."""
        self.clear()
        self._items.clear()
        for path in paths:
            item = QTreeWidgetItem([Path(path).name, "pending"])
            item.setData(0, _INPUT_PATH_ROLE, str(path))
            self.addTopLevelItem(item)
            self._items[str(path)] = item

    def set_status(self, path: str, status: str) -> None:
        """Update the status label for a single component."""
        item = self._items.get(str(path))
        if item is not None:
            item.setText(1, status)

    def add_output(self, component_path: str, stage: str, output_path: str) -> None:
        """Attach or update a produced output mesh as a selectable child of its component.

        stage is e.g. "meshed" or "uniformed". Children are keyed by their full
        output path (which encodes the parameter tag), so re-running the same
        parameters updates the existing node in place, while different
        parameter choices each get their own node for side-by-side comparison.
        """
        parent_item = self._items.get(str(component_path))
        if parent_item is None:
            return
        output_path_obj = Path(output_path)
        tag = _tag_label(output_path_obj)
        label = f"{stage} [{tag}]: {output_path_obj.name}"
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, _OUTPUT_PATH_ROLE) == str(output_path):
                child.setText(0, label)
                parent_item.setExpanded(True)
                return
        child = QTreeWidgetItem([label, "done"])
        child.setData(0, _OUTPUT_PATH_ROLE, str(output_path))
        child.setData(0, _STAGE_ROLE, stage)
        parent_item.addChild(child)
        parent_item.setExpanded(True)
        # Register the leaf itself too, so it can act as the parent for a
        # further pipeline stage (e.g. re-uniforming this exact meshed part
        # with different remesh parameters).
        self._items[str(output_path)] = child

    def set_outputs(self, paths: list[Path], root: Path | None = None) -> None:
        """Populate the tree directly from existing output mesh files, as a folder tree.

        Unlike set_components(), these items are immediately selectable/viewable
        (status "done") since no meshing/uniforming pipeline run is involved.
        When root is given, the tree mirrors the on-disk folder structure below
        it (e.g. meshed/<params>/... and uniformed/<params>/<params>/...), so
        runs with different parameters stay easy to browse and compare.
        """
        self.clear()
        self._items.clear()
        folder_items: dict[tuple[str, ...], QTreeWidgetItem] = {}

        def get_folder(parts: tuple[str, ...]):
            if not parts:
                return None
            if parts in folder_items:
                return folder_items[parts]
            parent_item = get_folder(parts[:-1])
            item = QTreeWidgetItem([parts[-1], ""])
            if parent_item is None:
                self.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
                parent_item.setExpanded(True)
            folder_items[parts] = item
            return item

        for path in paths:
            path = Path(path)
            rel = path.relative_to(root) if root is not None else Path(path.name)
            parent_item = get_folder(rel.parts[:-1])
            leaf = QTreeWidgetItem([rel.parts[-1], "done"])
            leaf.setData(0, _OUTPUT_PATH_ROLE, str(path))
            if parent_item is None:
                self.addTopLevelItem(leaf)
            else:
                parent_item.addChild(leaf)
            # Register so this loaded file can itself be a parent for a
            # further pipeline stage (e.g. re-uniforming a selected part).
            self._items[str(path)] = leaf

    def selected_output_paths(self) -> list[str]:
        """Return the output paths of the currently-selected (viewable) items."""
        return [
            item.data(0, _OUTPUT_PATH_ROLE) for item in self.selectedItems() if item.data(0, _OUTPUT_PATH_ROLE)
        ]

    def _on_selection_changed(self) -> None:
        self.component_selected.emit(self.selected_output_paths())
