"""Component tree widget: mirrors the discovered input files with per-item status.

Each input file may yield several meshed/uniformed output parts (STLs), so those
are added as selectable child nodes once the pipeline reports them done.

Every item - including folder nodes when browsing an existing output folder -
has a checkbox:
  - Checking a leaf shows that mesh in the viewer.
  - Checking a folder checks (and shows) every mesh under it at once.
  - Multi-selecting several items (ctrl/shift+click) and then toggling one of
    their checkboxes applies the same check state to the whole selection.

Every folder (any item with children) also gets a Scale spin box (default
1.0); leaves are shown in the viewer scaled by their nearest ancestor
folder's factor.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QDoubleSpinBox, QTreeWidget, QTreeWidgetItem

_INPUT_PATH_ROLE = Qt.ItemDataRole.UserRole
_OUTPUT_PATH_ROLE = Qt.ItemDataRole.UserRole + 1
_STAGE_ROLE = Qt.ItemDataRole.UserRole + 2
_SCALE_ROLE = Qt.ItemDataRole.UserRole + 3

_SCALE_COLUMN = 2

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


def _make_item(texts: list[str]) -> QTreeWidgetItem:
    """Create a tree item with an (initially unchecked) checkbox in column 0."""
    item = QTreeWidgetItem(texts)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(0, Qt.CheckState.Unchecked)
    return item


class ComponentTree(QTreeWidget):
    """Tree of components with a status column (pending/meshing/uniforming/done/error).

    Supports multi-selection (ctrl/shift+click) *and* checkboxes: emits
    component_selected with (output_path, scale) pairs for every currently
    checked item whenever a checkbox or scale factor changes, so the viewer
    panel can show several meshes at once - each at its own scale - in sync
    with what's ticked.
    """

    component_selected = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Component", "Status", "Scale"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._items: dict[str, QTreeWidgetItem] = {}
        self._updating_checks = False
        self.itemChanged.connect(self._on_item_changed)

    def _attach_scale_spinbox(self, item: QTreeWidgetItem) -> None:
        """Give a folder item its Scale spin box (default 1.0) - idempotent."""
        if self.itemWidget(item, _SCALE_COLUMN) is not None:
            return
        spin = QDoubleSpinBox()
        spin.setRange(0.001, 1000.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.1)
        spin.setValue(1.0)
        item.setData(0, _SCALE_ROLE, 1.0)
        spin.valueChanged.connect(lambda value, it=item: self._on_scale_changed(it, value))
        self.setItemWidget(item, _SCALE_COLUMN, spin)

    def _on_scale_changed(self, item: QTreeWidgetItem, value: float) -> None:
        item.setData(0, _SCALE_ROLE, value)
        self.component_selected.emit(self.checked_entries())

    def set_components(self, paths: list[Path]) -> None:
        """Rebuild the tree from a fresh list of component paths."""
        self.clear()
        self._items.clear()
        for path in paths:
            item = _make_item([Path(path).name, "pending"])
            item.setData(0, _INPUT_PATH_ROLE, str(path))
            self.addTopLevelItem(item)
            self._attach_scale_spinbox(item)
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
        child = _make_item([label, "done"])
        child.setData(0, _OUTPUT_PATH_ROLE, str(output_path))
        child.setData(0, _STAGE_ROLE, stage)
        parent_item.addChild(child)
        parent_item.setExpanded(True)
        # parent_item just gained a child, so it's now acting as a "folder" -
        # make sure it has a scale spin box (no-op if it already does).
        self._attach_scale_spinbox(parent_item)
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
        runs with different parameters stay easy to browse and compare. Every
        folder node gets a checkbox too, to view all meshes under it at once.
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
            item = _make_item([parts[-1], ""])
            if parent_item is None:
                self.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
                parent_item.setExpanded(True)
            self._attach_scale_spinbox(item)
            folder_items[parts] = item
            return item

        for path in paths:
            path = Path(path)
            rel = path.relative_to(root) if root is not None else Path(path.name)
            parent_item = get_folder(rel.parts[:-1])
            leaf = _make_item([rel.parts[-1], "done"])
            leaf.setData(0, _OUTPUT_PATH_ROLE, str(path))
            if parent_item is None:
                self.addTopLevelItem(leaf)
            else:
                parent_item.addChild(leaf)
            # Register so this loaded file can itself be a parent for a
            # further pipeline stage (e.g. re-uniforming a selected part).
            self._items[str(path)] = leaf

    def checked_output_paths(self) -> list[str]:
        """Return the output paths of every currently checked leaf item."""
        paths: list[str] = []

        def walk(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                walk(item.child(i))
            output_path = item.data(0, _OUTPUT_PATH_ROLE)
            if output_path and item.checkState(0) == Qt.CheckState.Checked:
                paths.append(output_path)

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return paths

    def checked_entries(self) -> list[tuple[str, float]]:
        """Return (output_path, scale) for every currently checked leaf item.

        scale is the item's own Scale spin box value if it has one (it became
        a "folder" by gaining children of its own), otherwise its nearest
        ancestor folder's factor.
        """

        def effective_scale(item: QTreeWidgetItem) -> float:
            node = item
            while node is not None:
                scale = node.data(0, _SCALE_ROLE)
                if scale is not None:
                    return scale
                node = node.parent()
            return 1.0

        entries: list[tuple[str, float]] = []

        def walk(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                walk(item.child(i))
            output_path = item.data(0, _OUTPUT_PATH_ROLE)
            if output_path and item.checkState(0) == Qt.CheckState.Checked:
                entries.append((output_path, effective_scale(item)))

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return entries

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or self._updating_checks:
            return
        self._updating_checks = True
        try:
            new_state = item.checkState(0)

            # If this item is part of a multi-selection (ctrl/shift+click),
            # apply the same check state to every other selected item too.
            selected = self.selectedItems()
            if item in selected and len(selected) > 1:
                for other in selected:
                    if other is not item:
                        self._set_check_state_recursive(other, new_state)

            # Checking/unchecking a folder cascades to every mesh under it.
            if item.childCount() > 0:
                self._set_children_check_state(item, new_state)

            self._update_ancestors_tristate(item)
        finally:
            self._updating_checks = False
        self.component_selected.emit(self.checked_entries())

    def _set_check_state_recursive(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        item.setCheckState(0, state)
        for i in range(item.childCount()):
            self._set_check_state_recursive(item.child(i), state)
        self._update_ancestors_tristate(item)

    def _set_children_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check_state(child, state)

    def _update_ancestors_tristate(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        while parent is not None:
            states = {parent.child(i).checkState(0) for i in range(parent.childCount())}
            if states == {Qt.CheckState.Checked}:
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif states == {Qt.CheckState.Unchecked}:
                parent.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
            parent = parent.parent()
