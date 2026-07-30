"""Bundled static assets (app icon, splash image)."""

from pathlib import Path

RESOURCES_DIR = Path(__file__).parent
ICON_PATH = RESOURCES_DIR / "Mesh.ico"
SPLASH_IMAGE_PATH = RESOURCES_DIR / "Mesh.png"
