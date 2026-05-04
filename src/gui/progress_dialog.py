"""
OmniClone Universal - Progress Dialog (Arabic RTL)
Displayed during the clone operation with live stats.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
import time


class ProgressDialog(QDialog):
    """
    Full-screen progress dialog shown during cloning.
    Displays: progress bar, speed, ETA, live log, and cancel button.
    """

    cancel_requested = pyqtSignal()

    def __init__(self, source_letter: str, target_letter: str, parent=None):
        super().__init__(parent)
        self.source_letter = source_letter
        self.target_letter = target_letter
        self._start_time   = time.monotonic()
        self._cancelled    = False

        self.setWindowTitle("OmniClone Universal — جارٍ النسخ")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(700, 500)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #0d1117;
                color: #e6edf3;
            }
            QLabel {
                color: #e6edf3;
                font-family: 'Segoe UI', Arial;
            }
            QTextEdit {
                background: #161b22;
                color: #58a6ff;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
            QPushButton#cancelBtn {
                background: #da3633;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 30px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton#cancelBtn:hover { background: #f85149; }
            QPushButton#cancelBtn:disabled { background: #484f58; color: #8b949e; }
            QProgressBar {
                border: none;
                border-radius: 8px;
                background: #21262d;
                height: 22px;
                text-align: center;
                color: #e6edf3;
                font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1f6feb, stop:1 #388bfd);
            }
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel(f"نسخ {self.source_letter}: ← {self.target_letter}:")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #388bfd;")
        layout.addWidget(title)

        # Status line
        self.status_label = QLabel("جارٍ الاتصال بالجهاز الهدف...")
        self.status_label.setFont(QFont("Segoe UI", 13))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(26)
        layout.addWidget(self.progress_bar)

        # Stats row
        stats_frame = QFrame()
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setSpacing(40)

        self.lbl_percent = self._stat_label("0%", "النسبة")
        self.lbl_speed   = self._stat_label("— MB/s", "السرعة")
        self.lbl_eta     = self._stat_label("—", "الوقت المتبقي")
        self.lbl_written = self._stat_label("0 GB / — GB", "المنقول")

        for w in [self.lbl_percent, self.lbl_speed, self.lbl_eta, self.lbl_written]:
            stats_layout.addWidget(w)

        layout.addWidget(stats_frame)

        # Log area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(160)
        layout.addWidget(self.log_area)

        # Cancel button
        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("إلغاء العملية")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setFixedWidth(200)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _stat_label(self, value: str, caption: str) -> QLabel:
        container = QFrame()
        container.setStyleSheet("""
            QFrame { background: #161b22; border-radius: 10px; padding: 6px; }
        """)
        v = QVBoxLayout(container)
        val_lbl = QLabel(value)
        val_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setStyleSheet("color: #58a6ff;")
        cap_lbl = QLabel(caption)
        cap_lbl.setFont(QFont("Segoe UI", 10))
        cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap_lbl.setStyleSheet("color: #8b949e;")
        v.addWidget(val_lbl)
        v.addWidget(cap_lbl)
        # store value label reference on container
        container._val_lbl = val_lbl
        return container

    def update_progress(self, sent: int, total: int, pct: float, speed_mb: float):
        self.progress_bar.setValue(int(pct))

        self.lbl_percent._val_lbl.setText(f"{pct:.1f}%")
        self.lbl_speed._val_lbl.setText(f"{speed_mb:.1f} MB/s")

        elapsed = time.monotonic() - self._start_time
        if speed_mb > 0:
            remaining_bytes = total - sent
            eta_sec = (remaining_bytes / (1024 * 1024)) / speed_mb
            eta_str = self._format_time(eta_sec)
        else:
            eta_str = "—"
        self.lbl_eta._val_lbl.setText(eta_str)

        sent_gb  = sent  / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        self.lbl_written._val_lbl.setText(f"{sent_gb:.2f} / {total_gb:.2f} GB")

    def _format_time(self, seconds: float) -> str:
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def set_status(self, msg: str):
        self.status_label.setText(msg)
        self.log_area.append(msg)
        # Auto-scroll
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_done(self, success: bool, message: str):
        self.cancel_btn.setEnabled(False)
        if success:
            self.status_label.setText("✔ اكتملت العملية بنجاح!")
            self.status_label.setStyleSheet("color: #3fb950; font-size: 16px; font-weight: bold;")
            self.progress_bar.setValue(100)
        else:
            self.status_label.setText(f"✖ فشلت العملية: {message}")
            self.status_label.setStyleSheet("color: #f85149; font-size: 14px; font-weight: bold;")
        self.log_area.append(f"\n{'✔' if success else '✖'} {message}")
        # Change cancel to close
        self.cancel_btn.setText("إغلاق")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setStyleSheet("""
            QPushButton { background: #238636; color: white; border: none;
                          border-radius: 8px; padding: 10px 30px;
                          font-size: 15px; font-weight: bold; }
            QPushButton:hover { background: #2ea043; }
        """)
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.accept)

    def _on_cancel(self):
        if not self._cancelled:
            self._cancelled = True
            self.cancel_btn.setEnabled(False)
            self.set_status("جارٍ إلغاء العملية...")
            self.cancel_requested.emit()
