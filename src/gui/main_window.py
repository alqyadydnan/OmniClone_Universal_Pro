"""
OmniClone Universal - Main Window (Arabic RTL PyQt6)
Professional Right-to-Left interface for IT engineers.
"""

import os
import sys
import threading
from typing import List, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFrame, QSplitter, QMessageBox, QComboBox,
    QGroupBox, QStatusBar, QApplication, QSizePolicy,
    QProgressBar, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QSize, QTimer
from PyQt6.QtGui import (
    QFont, QIcon, QColor, QPalette, QPixmap, QAction
)

from ..engine.partition_reader import list_local_partitions
from ..engine.cloner import ClonerEngine
from ..services.network_manager import NetworkManager
from ..protocol.messages import PartitionInfo
from .progress_dialog import ProgressDialog


# ──────────────────────────────────────────────────────────
# Stylesheet — Dark Professional Theme
# ──────────────────────────────────────────────────────────
STYLE = """
QMainWindow, QWidget#centralWidget {
    background: #0d1117;
}
QLabel {
    color: #e6edf3;
    font-family: 'Segoe UI', 'Tahoma', Arial;
}
QGroupBox {
    color: #8b949e;
    font-family: 'Segoe UI', 'Tahoma', Arial;
    font-size: 13px;
    font-weight: bold;
    border: 1px solid #30363d;
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top right;
    right: 16px;
    padding: 2px 8px;
    background: #161b22;
    border-radius: 6px;
    color: #58a6ff;
}
QListWidget {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    color: #e6edf3;
    font-family: 'Segoe UI', 'Tahoma', Arial;
    font-size: 13px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px 4px;
}
QListWidget::item:selected {
    background: #1f6feb;
    color: white;
}
QListWidget::item:hover:!selected {
    background: #21262d;
}
QPushButton {
    background: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 9px 18px;
    font-family: 'Segoe UI', 'Tahoma', Arial;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover { background: #292f38; border-color: #58a6ff; }
QPushButton:pressed { background: #1f6feb; }
QPushButton:disabled { background: #161b22; color: #484f58; border-color: #21262d; }
QPushButton#startBtn {
    background: #238636;
    color: white;
    border: none;
    font-size: 16px;
    padding: 14px 40px;
    border-radius: 10px;
}
QPushButton#startBtn:hover { background: #2ea043; }
QPushButton#startBtn:disabled { background: #161b22; color: #484f58; }
QPushButton#refreshBtn {
    background: #1f6feb;
    color: white;
    border: none;
    padding: 8px 16px;
}
QPushButton#refreshBtn:hover { background: #388bfd; }
QStatusBar {
    background: #161b22;
    color: #8b949e;
    border-top: 1px solid #30363d;
    font-family: 'Segoe UI', Arial;
}
QFrame#divider {
    background: #30363d;
    max-width: 1px;
}
QLabel#warningBanner {
    background: #3d1c02;
    color: #f0883e;
    border: 1px solid #bd561d;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}
QLabel#successBanner {
    background: #0d2119;
    color: #3fb950;
    border: 1px solid #238636;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}
"""


def _fmt_size(b: int) -> str:
    if b >= 1024 ** 3:
        return f"{b / 1024**3:.1f} GB"
    elif b >= 1024 ** 2:
        return f"{b / 1024**2:.1f} MB"
    return f"{b / 1024:.0f} KB"


# ──────────────────────────────────────────────────────────
# Partition Card Widget
# ──────────────────────────────────────────────────────────
class PartitionCard(QListWidgetItem):
    """List item representing one partition with detailed info."""

    def __init__(self, part: PartitionInfo, is_target: bool = False):
        super().__init__()
        self.partition = part
        icon = "🖥" if part.is_system else "💾"
        label = part.label or "بدون اسم"
        used  = _fmt_size(part.used_bytes)
        total = _fmt_size(part.size_bytes)
        pct   = (part.used_bytes / part.size_bytes * 100) if part.size_bytes > 0 else 0

        lines = [
            f"{icon}  القسم {part.letter}:  —  {label}",
            f"     {part.fs}  |  {used} مستخدم من {total}  ({pct:.0f}%)",
        ]
        if is_target and part.is_system:
            lines.append("     ⚠  قسم النظام — سيُستبدل بالكامل")

        self.setText("\n".join(lines))
        self.setFont(QFont("Segoe UI", 12))
        self.setSizeHint(QSize(300, 68))

        if part.is_system:
            self.setForeground(QColor("#f0883e"))


# ──────────────────────────────────────────────────────────
# Worker signals
# ──────────────────────────────────────────────────────────
class WorkerSignals(QObject):
    target_connected  = pyqtSignal(str, list)   # (ip, partitions)
    status_update     = pyqtSignal(str)
    progress_update   = pyqtSignal(int, int, float, float)  # sent, total, pct, speed
    clone_done        = pyqtSignal(bool, str)


# ──────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────
class MainWindow(QMainWindow):

    def __init__(self, tftp_root: str):
        super().__init__()
        self.tftp_root         = tftp_root
        self.source_partitions: List[PartitionInfo] = []
        self.target_partitions: List[PartitionInfo] = []
        self.target_ip: Optional[str]                = None
        self.selected_source: Optional[PartitionInfo] = None
        self.selected_target: Optional[PartitionInfo] = None
        self._cloner: Optional[ClonerEngine]          = None
        self._progress_dlg: Optional[ProgressDialog]  = None

        self.signals = WorkerSignals()
        self.signals.target_connected.connect(self._on_target_connected)
        self.signals.status_update.connect(self._on_status)
        self.signals.progress_update.connect(self._on_progress)
        self.signals.clone_done.connect(self._on_clone_done)

        self._network = NetworkManager(
            tftp_root=tftp_root,
            on_target_connected=lambda ip, parts: self.signals.target_connected.emit(ip, parts),
            on_status=lambda msg: self.signals.status_update.emit(msg),
        )

        self._setup_ui()
        self._load_source_partitions()

    # ──────────────────────────────────────────────────────
    # UI Setup
    # ──────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle("OmniClone Universal — نظام النسخ الذكي")
        self.setMinimumSize(1100, 720)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(20, 16, 20, 12)

        # Header
        root.addWidget(self._build_header())

        # Warning banner
        self.warn_banner = QLabel(
            "⚠  تحذير: تأكد من اختيار القسم الصحيح. الكتابة فوق قسم خاطئ تؤدي لفقدان البيانات نهائياً."
        )
        self.warn_banner.setObjectName("warningBanner")
        self.warn_banner.setWordWrap(True)
        self.warn_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.warn_banner)

        # Main panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #30363d; }")
        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_target_panel())
        splitter.setSizes([500, 500])
        root.addWidget(splitter, 1)

        # Network services row
        root.addWidget(self._build_services_row())

        # Start button
        root.addWidget(self._build_start_row())

        # Status bar
        self.statusBar().showMessage("جاهز — قم بتشغيل خدمات الشبكة لبدء اكتشاف الجهاز الهدف")

    def _build_header(self) -> QWidget:
        w = QFrame()
        w.setStyleSheet("""
            QFrame {
                background: #161b22;
                border-radius: 12px;
                padding: 6px;
            }
        """)
        h = QHBoxLayout(w)
        h.setContentsMargins(20, 10, 20, 10)

        logo_label = QLabel("⚡")
        logo_label.setFont(QFont("Segoe UI", 28))
        h.addWidget(logo_label)

        title_col = QVBoxLayout()
        title = QLabel("OmniClone Universal Pro")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #58a6ff;")
        subtitle = QLabel("نظام نسخ الأنظمة الذكي عبر الشبكة المباشرة — لمهندسي تقنية المعلومات")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet("color: #8b949e;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        h.addLayout(title_col)
        h.addStretch()

        version = QLabel("v1.0 Pro")
        version.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        h.addWidget(version)
        return w

    def _build_source_panel(self) -> QWidget:
        group = QGroupBox("الجهاز المصدر (Source)")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Subtitle
        info = QLabel("اختر القسم المراد نسخه (للقراءة فقط — لن يُلمس)")
        info.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(info)

        # Partition list
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.source_list.itemSelectionChanged.connect(self._on_source_selected)
        layout.addWidget(self.source_list, 1)

        # Source detail
        self.source_detail = QLabel("لم يتم الاختيار بعد")
        self.source_detail.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.source_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.source_detail)

        # Refresh button
        refresh_btn = QPushButton("↻  تحديث قائمة الأقسام")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.clicked.connect(self._load_source_partitions)
        layout.addWidget(refresh_btn)

        return group

    def _build_target_panel(self) -> QWidget:
        group = QGroupBox("الجهاز الهدف (Target)")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Subtitle
        info = QLabel("أقسام الجهاز الهدف — ستظهر بعد الإقلاع عبر PXE")
        info.setStyleSheet("color: #8b949e; font-size: 12px;")
        layout.addWidget(info)

        # Target status
        self.target_status = QLabel("⏳  في انتظار اتصال الجهاز الهدف...")
        self.target_status.setStyleSheet("color: #f0883e; font-weight: bold; font-size: 13px;")
        self.target_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.target_status)

        # Partition list
        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.target_list.setEnabled(False)
        self.target_list.itemSelectionChanged.connect(self._on_target_selected)
        layout.addWidget(self.target_list, 1)

        # Safety lock notice
        self.lock_notice = QLabel(
            "🔒  بمجرد البدء، ستُقفل جميع الأقسام الأخرى تلقائياً لضمان السلامة الكاملة"
        )
        self.lock_notice.setStyleSheet("color: #3fb950; font-size: 12px;")
        self.lock_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lock_notice.setWordWrap(True)
        layout.addWidget(self.lock_notice)

        # Target detail
        self.target_detail = QLabel("لم يتم الاختيار بعد")
        self.target_detail.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.target_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.target_detail)

        return group

    def _build_services_row(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #161b22; border-radius: 10px; }")
        h = QHBoxLayout(frame)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(12)

        services_lbl = QLabel("خدمات الشبكة:")
        services_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        h.addWidget(services_lbl)

        self.dhcp_indicator  = self._service_dot("DHCP", False)
        self.tftp_indicator  = self._service_dot("TFTP", False)
        self.agent_indicator = self._service_dot("الوكيل", False)

        h.addWidget(self.dhcp_indicator)
        h.addWidget(self.tftp_indicator)
        h.addWidget(self.agent_indicator)
        h.addStretch()

        self.start_services_btn = QPushButton("▶  تشغيل خدمات الشبكة")
        self.start_services_btn.setObjectName("refreshBtn")
        self.start_services_btn.clicked.connect(self._start_network_services)
        h.addWidget(self.start_services_btn)

        return frame

    def _service_dot(self, label: str, active: bool) -> QLabel:
        color = "#3fb950" if active else "#484f58"
        dot = QLabel(f"● {label}")
        dot.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
        return dot

    def _build_start_row(self) -> QWidget:
        frame = QFrame()
        h = QHBoxLayout(frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        # Summary
        self.summary_label = QLabel("اختر القسم المصدر والهدف لبدء النسخ")
        self.summary_label.setStyleSheet("color: #8b949e; font-size: 13px;")
        h.addWidget(self.summary_label, 1)

        self.start_btn = QPushButton("⚡  بدء النسخ الآن")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setEnabled(False)
        self.start_btn.setFixedHeight(54)
        self.start_btn.clicked.connect(self._confirm_and_start)
        h.addWidget(self.start_btn)

        return frame

    # ──────────────────────────────────────────────────────
    # Logic
    # ──────────────────────────────────────────────────────
    def _load_source_partitions(self):
        self.source_list.clear()
        self.statusBar().showMessage("جارٍ فحص الأقسام المحلية...")
        try:
            self.source_partitions = list_local_partitions()
            for p in self.source_partitions:
                card = PartitionCard(p, is_target=False)
                self.source_list.addItem(card)
            self.statusBar().showMessage(
                f"تم العثور على {len(self.source_partitions)} قسم على الجهاز المصدر."
            )
        except Exception as e:
            self.statusBar().showMessage(f"خطأ في فحص الأقسام: {e}")
            # In non-Windows environment, show placeholder
            self._load_demo_source_partitions()

    def _load_demo_source_partitions(self):
        """Demo mode when not running on Windows (development)."""
        from ..protocol.messages import PartitionInfo
        demos = [
            PartitionInfo("C", "Windows", "NTFS", 500*1024**3, 120*1024**3,
                          "\\\\.\\C:", 0, 0, 1048576, True, True),
            PartitionInfo("D", "Data", "NTFS", 1000*1024**3, 450*1024**3,
                          "\\\\.\\D:", 1, 0, 500*1024**3, False, False),
        ]
        self.source_partitions = demos
        for p in demos:
            card = PartitionCard(p)
            self.source_list.addItem(card)

    def _start_network_services(self):
        self.start_services_btn.setEnabled(False)
        self.start_services_btn.setText("خدمات الشبكة تعمل...")
        self.dhcp_indicator.setText("● DHCP")
        self.dhcp_indicator.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        self.tftp_indicator.setText("● TFTP")
        self.tftp_indicator.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        self._network.start_services()
        self.statusBar().showMessage(
            "خدمات DHCP و TFTP تعمل. أقلع الجهاز الهدف عبر PXE الآن..."
        )

    def _on_source_selected(self):
        items = self.source_list.selectedItems()
        if not items:
            return
        card: PartitionCard = items[0]
        self.selected_source = card.partition
        used  = _fmt_size(self.selected_source.used_bytes)
        total = _fmt_size(self.selected_source.size_bytes)
        self.source_detail.setText(
            f"القسم المختار: {self.selected_source.letter}:  |  "
            f"{used} مستخدم من {total}  |  {self.selected_source.fs}"
        )
        self.source_detail.setStyleSheet("color: #58a6ff; font-size: 13px; font-weight: bold;")
        self._update_start_button()

    def _on_target_selected(self):
        items = self.target_list.selectedItems()
        if not items:
            return
        card: PartitionCard = items[0]
        self.selected_target = card.partition
        used  = _fmt_size(self.selected_target.used_bytes)
        total = _fmt_size(self.selected_target.size_bytes)
        self.target_detail.setText(
            f"الهدف: {self.selected_target.letter}:  |  "
            f"{used} مستخدم من {total}  |  {self.selected_target.fs}"
        )
        self.target_detail.setStyleSheet("color: #f0883e; font-size: 13px; font-weight: bold;")
        self._update_start_button()

    def _on_target_connected(self, ip: str, partitions: List[PartitionInfo]):
        self.target_ip = ip
        self.target_partitions = partitions

        self.target_status.setText(f"✔  متصل بـ {ip} — {len(partitions)} قسم")
        self.target_status.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")
        self.agent_indicator.setText("● الوكيل")
        self.agent_indicator.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 13px;")

        self.target_list.clear()
        self.target_list.setEnabled(True)
        for p in partitions:
            card = PartitionCard(p, is_target=True)
            self.target_list.addItem(card)

        self.statusBar().showMessage(
            f"الجهاز الهدف ({ip}) متصل. اختر قسم الهدف لبدء النسخ."
        )

    def _on_status(self, msg: str):
        self.statusBar().showMessage(msg)
        if self._progress_dlg:
            self._progress_dlg.set_status(msg)

    def _on_progress(self, sent: int, total: int, pct: float, speed: float):
        if self._progress_dlg:
            self._progress_dlg.update_progress(sent, total, pct, speed)

    def _on_clone_done(self, success: bool, message: str):
        if self._progress_dlg:
            self._progress_dlg.set_done(success, message)
        self.start_btn.setEnabled(True)

    def _update_start_button(self):
        ready = (self.selected_source is not None and
                 self.selected_target is not None and
                 self.target_ip is not None)
        self.start_btn.setEnabled(ready)
        if ready:
            src = self.selected_source.letter
            tgt = self.selected_target.letter
            used = _fmt_size(self.selected_source.used_bytes)
            self.summary_label.setText(
                f"سيتم نسخ {used} من القسم {src}: إلى القسم {tgt}: على الجهاز الهدف"
            )
            self.summary_label.setStyleSheet("color: #e6edf3; font-size: 13px;")

    def _confirm_and_start(self):
        if not self.selected_source or not self.selected_target:
            return

        src = self.selected_source.letter
        tgt = self.selected_target.letter
        used = _fmt_size(self.selected_source.used_bytes)

        # Double-confirmation dialog
        msg = QMessageBox(self)
        msg.setWindowTitle("تأكيد عملية النسخ")
        msg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        msg.setText(
            f"<b>هل أنت متأكد تماماً؟</b><br><br>"
            f"سيتم نسخ القسم <b style='color:#58a6ff'>{src}:</b> "
            f"({used}) إلى القسم <b style='color:#f85149'>{tgt}:</b> "
            f"على الجهاز الهدف.<br><br>"
            f"<b style='color:#f85149'>⚠  سيتم محو كل البيانات الموجودة على {tgt}: نهائياً.</b><br>"
            f"ستُقفل جميع الأقسام الأخرى على الهدف تلقائياً."
        )
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.button(QMessageBox.StandardButton.Yes).setText("نعم، ابدأ النسخ")
        msg.button(QMessageBox.StandardButton.No).setText("إلغاء")
        msg.setStyleSheet("""
            QMessageBox { background: #161b22; color: #e6edf3; }
            QLabel { color: #e6edf3; font-family: 'Segoe UI', Arial; font-size: 13px; }
            QPushButton { padding: 8px 20px; font-size: 13px; }
        """)

        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        # Second confirmation — type partition letter
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "تأكيد ثانٍ",
            f"اكتب حرف القسم الهدف ({tgt}) للتأكيد:"
        )
        if not ok or text.strip().upper() != tgt.upper():
            QMessageBox.warning(self, "إلغاء", "لم يتطابق الحرف. تم إلغاء العملية.")
            return

        self._start_clone()

    def _start_clone(self):
        self.start_btn.setEnabled(False)

        # Show progress dialog
        self._progress_dlg = ProgressDialog(
            self.selected_source.letter,
            self.selected_target.letter,
            parent=self
        )
        self._progress_dlg.cancel_requested.connect(self._cancel_clone)

        # Send target selection to agent and start clone
        def _do_start():
            try:
                success, msg = self._network.send_target_selection(self.selected_target)
                if not success:
                    self.signals.clone_done.emit(False, f"فشل إرسال الاختيار: {msg}")
                    return
            except Exception as e:
                self.signals.clone_done.emit(False, str(e))
                return

            self._cloner = ClonerEngine(
                source_partition=self.selected_source,
                target_ip=self.target_ip,
                on_progress=lambda s, t, p, sp: self.signals.progress_update.emit(s, t, p, sp),
                on_status=lambda m: self.signals.status_update.emit(m),
                on_done=lambda ok, m: self.signals.clone_done.emit(ok, m),
            )
            self._cloner.start()

        threading.Thread(target=_do_start, daemon=True).start()
        self._progress_dlg.exec()

    def _cancel_clone(self):
        if self._cloner:
            self._cloner.stop()

    def closeEvent(self, event):
        self._network.stop_services()
        event.accept()
