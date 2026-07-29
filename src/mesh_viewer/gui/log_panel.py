"""Log/console panel for processing messages and errors."""

from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit


class LogPanel(QPlainTextEdit):
    """Read-only log output; appends timestamped messages from worker threads."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)

    def append_message(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.appendPlainText(f"[{timestamp}] {level.upper()}: {message}")
