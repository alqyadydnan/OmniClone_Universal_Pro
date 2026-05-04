"""
OmniClone Universal Pro — Main Entry Point (Source Machine)
Run this on the SOURCE (master) machine as Administrator.
"""

import sys
import os
import ctypes
import logging

# ── Logging setup ──────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "OmniClone.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("omniclone.main")


def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _require_admin():
    """Re-launch as Administrator if not already elevated."""
    if not _is_admin():
        logger.warning("Not running as Administrator. Relaunching with elevation...")
        params = " ".join(f'"{a}"' for a in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        sys.exit(0)


def _get_tftp_root() -> str:
    """
    Determine the TFTP boot files root directory.
    In packaged EXE: <exe_dir>/boot/
    In development:  <project_root>/boot/
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.join(base, "boot")
    os.makedirs(root, exist_ok=True)
    return root


def main():
    _require_admin()

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setApplicationName("OmniClone Universal Pro")
    app.setOrganizationName("OmniClone")

    # Set global Arabic-friendly font
    font = QFont("Segoe UI", 12)
    app.setFont(font)

    tftp_root = _get_tftp_root()
    logger.info(f"TFTP root: {tftp_root}")

    from .gui.main_window import MainWindow
    window = MainWindow(tftp_root=tftp_root)
    window.showMaximized()

    logger.info("OmniClone Universal Pro started.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
