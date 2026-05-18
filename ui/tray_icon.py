"""
Clipboard_Master — 系统托盘图标
提供托盘图标、右键菜单、状态切换与退出功能。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QFont
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication


def _create_tray_icon_pixmap(size: int = 64) -> QPixmap:
    """
    使用 QPainter 在内存中绘制一个剪贴板图标 (没有外部图片依赖)。
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 主体圆角矩形 (剪贴板板面)
    margin = 4
    body_rect = pixmap.rect().adjusted(margin, margin + 4, -margin, -margin)
    painter.setBrush(QBrush(QColor("#4A90D9")))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(body_rect, size * 0.15, size * 0.15)

    # 顶部夹子 (小块)
    clip_w = size * 0.35
    clip_h = size * 0.12
    clip_x = (size - clip_w) / 2
    clip_y = margin
    painter.setBrush(QBrush(QColor("#357ABD")))
    painter.drawRoundedRect(int(clip_x), int(clip_y), int(clip_w), int(clip_h), 3, 3)

    # 文字线条 (模拟剪贴板上的内容)
    painter.setPen(QPen(QColor("#FFFFFF"), max(1, size * 0.03)))
    line_y_start = margin + clip_h + body_rect.height() * 0.25
    line_spacing = body_rect.height() * 0.18
    line_left = margin + size * 0.18
    for i in range(3):
        y = line_y_start + i * line_spacing
        right_x = int(size - margin - size * 0.18)
        painter.drawLine(int(line_left), int(y), right_x, int(y))

    painter.end()
    return pixmap


class TrayIcon(QSystemTrayIcon):
    """
    系统托盘图标

    信号:
      show_panel_requested — 用户点击"显示面板"时发出
      clear_requested      — 用户点击"清空历史"时发出
      quit_requested       — 用户点击"退出"时发出
      monitoring_toggled   — 监听暂停/恢复，参数 bool
    """

    show_panel_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    monitoring_toggled = pyqtSignal(bool)
    hotkey_change_requested = pyqtSignal()  # 用户请求更改热键

    def __init__(self, parent=None):
        super().__init__(parent)

        self._monitoring_enabled = True
        self._build_icon()
        self._build_menu()
        self._connect_signals()

    def _build_icon(self):
        """生成并设置托盘图标"""
        pixmap = _create_tray_icon_pixmap()
        self.setIcon(QIcon(pixmap))
        self._current_hotkey = "Ctrl+Shift+C"
        self._update_tooltip()

    def _build_menu(self):
        """构建右键菜单"""
        menu = QMenu()

        # 显示面板
        show_action = QAction("📋 显示历史面板", menu)
        show_action.triggered.connect(self.show_panel_requested.emit)
        menu.addAction(show_action)

        menu.addSeparator()

        # 暂停 / 恢复监听
        self.toggle_action = QAction("⏸ 暂停监听", menu)
        self.toggle_action.triggered.connect(self._toggle_monitoring)
        menu.addAction(self.toggle_action)

        # 清空历史
        clear_action = QAction("🗑 清空历史", menu)
        clear_action.triggered.connect(self.clear_requested.emit)
        menu.addAction(clear_action)

        menu.addSeparator()

        # 更改热键
        hotkey_action = QAction("⌨ 更改热键…", menu)
        hotkey_action.triggered.connect(self.hotkey_change_requested.emit)
        menu.addAction(hotkey_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("❌ 退出", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        # 样式
        menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 28px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: #e3f2fd;
                color: #1976d2;
            }
            QMenu::separator {
                height: 1px;
                background: #eee;
                margin: 4px 8px;
            }
        """)

        self.setContextMenu(menu)

    def _connect_signals(self):
        """连接托盘内置信号"""
        # 单击托盘图标 → 显示面板
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        """托盘图标点击事件"""
        if reason == QSystemTrayIcon.Trigger:  # 左键单击
            self.show_panel_requested.emit()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.show_panel_requested.emit()

    def _toggle_monitoring(self):
        """切换监听状态"""
        self._monitoring_enabled = not self._monitoring_enabled
        status = "监听中" if self._monitoring_enabled else "已暂停"
        if self._monitoring_enabled:
            self.toggle_action.setText("⏸ 暂停监听")
        else:
            self.toggle_action.setText("▶ 恢复监听")
        self.setToolTip(f"Clipboard Master — {status}\n"
                        f"快捷键: {self._current_hotkey}")
        self.monitoring_toggled.emit(self._monitoring_enabled)

    def _update_tooltip(self):
        """根据当前热键更新托盘提示文字"""
        self.setToolTip("Clipboard Master — 剪贴板历史管理\n"
                        f"快捷键: {self._current_hotkey} 唤醒面板")

    def set_hotkey(self, hotkey: str):
        """由外部调用，更新显示的热键文本"""
        self._current_hotkey = hotkey
        self._update_tooltip()

    def notify(self, title: str, message: str):
        """弹出系统通知气泡"""
        self.showMessage(title, message, QSystemTrayIcon.Information, 3000)

    def is_monitoring(self) -> bool:
        return self._monitoring_enabled
