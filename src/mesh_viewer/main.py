"""Application entry point."""

import sys

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from mesh_viewer.gui.main_window import MainWindow
from mesh_viewer.resources import ICON_PATH, SPLASH_IMAGE_PATH


def _set_windows_app_user_model_id() -> None:
    """On Windows, give this process its own taskbar identity.

    Without this, a script launched via python.exe gets grouped under
    python.exe's own taskbar icon/identity instead of ours, no matter what
    QApplication.setWindowIcon()/QWidget.setWindowIcon() are set to - this is
    the standard fix for "the taskbar icon doesn't change". Must run before
    QApplication (and any window) is created. No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MeshViewer.App")
    except Exception:
        pass  # best-effort - never block startup over this


def main() -> None:
    """Launch the Mesh Viewer GUI."""
    _set_windows_app_user_model_id()

    app = QApplication(sys.argv)
    # Sets the taskbar/window icon for the whole application (fallback for any
    # window that doesn't set its own); MainWindow also sets it explicitly.
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    splash = QSplashScreen(QPixmap(str(SPLASH_IMAGE_PATH)))
    splash.show()
    app.processEvents()

    window = MainWindow()
    window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
