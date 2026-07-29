# Mesh Viewer

GUI pipeline for importing CAD assemblies, meshing/uniforming components in the
background, and inspecting the resulting meshes in an interactive 3D viewer.

See [mesh_plan.md](mesh_plan.md) for the full design plan and to-do list.

## Layout

```
src/mesh_viewer/
    main.py            # application entry point
    gui/                # PySide6 windows/widgets
    core/               # meshing + uniforming pipeline wrappers
    io/                 # file discovery / output writing
tests/
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Run

```powershell
mesh-viewer
```
