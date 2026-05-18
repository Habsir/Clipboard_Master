"""
Clipboard_Master — 历史记录弹出面板

无边框浮动窗口，在鼠标位置附近弹出。
特性: 搜索过滤 · 网格瀑布流布局 · 失焦/ESC 自动隐藏 · 阴影效果
"""
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                              QScrollArea, QLabel, QPushButton, QApplication,
                              QFrame, QGridLayout, QGraphicsDropShadowEffect,
                              QMessageBox)

from ui.list_item import ListItemWidget


class HistoryPanel(QWidget):
    """
    剪贴板历史弹出面板

    用法:
        panel = HistoryPanel(db_manager)
        panel.show_at(QCursor.pos())   # 在鼠标位置弹出
    """

    # 面板关闭信号
    panel_closed = pyqtSignal()

    # ─── 布局常量 ───
    PANEL_WIDTH = 680
    PANEL_HEIGHT = 500
    COLUMNS = 3                # 网格列数
    ITEM_SPACING = 8           # 卡片间距

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._all_records = []
        self._is_visible = False
        self.grid_layout = None  # 网格布局容器，_rebuild_grid 中复用，不销毁重建

        self._init_ui()
        self._apply_styles()

    # ─── UI 构建 ──────────────────────────────────────

    def _init_ui(self):
        """初始化无边框弹出窗口"""
        # 窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.PANEL_WIDTH, self.PANEL_HEIGHT)

        # ── 根布局 ──
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ── 白色内容容器 ──
        self.frame = QFrame(self)
        self.frame.setObjectName("contentFrame")
        content = QVBoxLayout(self.frame)
        content.setContentsMargins(14, 10, 14, 14)
        content.setSpacing(8)

        # ── 标题栏 ──
        header = QHBoxLayout()
        title = QLabel("📋 剪贴板历史")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #333;")
        header.addWidget(title)
        header.addStretch()

        self.count_label = QLabel("共 0 条")
        self.count_label.setStyleSheet("color: #999; font-size: 11px;")
        header.addWidget(self.count_label)

        clear_btn = QPushButton("清空全部")
        clear_btn.setObjectName("clearBtn")
        clear_btn.setFixedSize(78, 28)
        clear_btn.clicked.connect(self._on_clear_all)
        header.addWidget(clear_btn)

        # ── 关闭按钮 ──
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("关闭面板 (Esc)")
        close_btn.clicked.connect(self.hide_panel)
        header.addWidget(close_btn)

        content.addLayout(header)

        # ── 搜索框 ──
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索历史记录…")
        self.search_input.setFixedHeight(34)
        self.search_input.textChanged.connect(self._on_search)
        content.addWidget(self.search_input)

        # ── 滚动区域 ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setObjectName("scrollArea")
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.scroll_content = QWidget()
        self.scroll.setWidget(self.scroll_content)
        self.grid_layout = None
        content.addWidget(self.scroll)

        root.addWidget(self.frame)

        # ── 阴影效果 ──
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(0, 4)
        self.frame.setGraphicsEffect(shadow)

    def _apply_styles(self):
        self.setStyleSheet("""
            #contentFrame {
                background: #ffffff;
                border-radius: 14px;
                border: 1px solid #e0e0e0;
            }
            #scrollArea {
                background: #fafafa;
                border-radius: 8px;
            }
            QScrollArea { background: transparent; }
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 17px;
                padding: 4px 14px;
                font-size: 13px;
                background: #f5f5f5;
            }
            QLineEdit:focus {
                border-color: #4a90d9;
                background: #fff;
            }
            #clearBtn {
                background: #ff6b6b;
                color: white;
                border: none;
                border-radius: 14px;
                font-size: 12px;
                font-weight: bold;
            }
            #clearBtn:hover { background: #ee5555; }
            #closeBtn {
                background: transparent;
                color: #999;
                border: 1px solid #ddd;
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
            }
            #closeBtn:hover {
                background: #ff6b6b;
                color: white;
                border-color: #ff6b6b;
            }
        """)

    # ─── 显示 / 隐藏 ─────────────────────────────────

    def show_at(self, global_pos: QPoint):
        """
        在指定全局坐标附近弹出面板，
        自动修正位置以确保完全在屏幕可见区域内。
        """
        screen = QApplication.screenAt(global_pos) or \
                 QApplication.primaryScreen()
        if screen is None:
            return

        geo = screen.availableGeometry()
        x = global_pos.x()
        y = global_pos.y() + 20  # 略低于鼠标

        # 水平修正
        if x + self.PANEL_WIDTH > geo.right():
            x = geo.right() - self.PANEL_WIDTH - 10
        if x < geo.left():
            x = geo.left() + 10

        # 垂直修正
        if y + self.PANEL_HEIGHT > geo.bottom():
            y = global_pos.y() - self.PANEL_HEIGHT - 10
        if y < geo.top():
            y = geo.top() + 10

        self.move(x, y)
        self._refresh()
        self.show()
        self.activateWindow()
        self.search_input.setFocus()
        self._is_visible = True

    def hide_panel(self):
        self.hide()
        self._is_visible = False
        self.panel_closed.emit()

    def is_visible(self) -> bool:
        return self._is_visible

    # ─── 数据加载 ────────────────────────────────────

    def _refresh(self, search_query: str = None):
        """从数据库拉取记录并重建网格"""
        try:
            self._all_records = self.db_manager.get_records(
                limit=50,
                search_query=search_query
            )
        except Exception as e:
            print(f"[HistoryPanel] 加载失败: {e}")
            self._all_records = []

        self._rebuild_grid()
        self.count_label.setText(f"共 {len(self._all_records)} 条")

    def _rebuild_grid(self):
        """
        按 COLUMNS 列重新渲染卡片。

        ★ 关键设计：复用 self.grid_layout，绝不销毁后重建。
        原因：deleteLater() 是延迟删除，紧接着创建新布局会导致
        Qt 冲突警告且新布局设置失败 → 卡片不可见（交替空白bug）。
        """
        # ── 首次调用：创建网格布局 ──
        if self.grid_layout is None:
            self.grid_layout = QGridLayout(self.scroll_content)
            self.grid_layout.setContentsMargins(4, 4, 4, 4)
            self.grid_layout.setSpacing(self.ITEM_SPACING)
        else:
            # ── 后续调用：仅清除旧卡片，保留布局容器 ──
            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        # ── 填充卡片 ──
        for i, record in enumerate(self._all_records):
            row = i // self.COLUMNS
            col = i % self.COLUMNS
            card = ListItemWidget(record)
            self.grid_layout.addWidget(
                card, row, col, Qt.AlignTop | Qt.AlignLeft
            )

        # 底部弹性空白
        last_row = (max(0, len(self._all_records) - 1) // self.COLUMNS)
        self.grid_layout.setRowStretch(last_row + 1, 1)

    # ─── 公开方法 ────────────────────────────────────

    def delete_record_by_id(self, record_id: int):
        try:
            self.db_manager.delete_record(record_id)
            self._refresh()
        except Exception as e:
            print(f"[HistoryPanel] 删除失败: {e}")

    # ─── 槽函数 ──────────────────────────────────────

    def _on_search(self, text: str):
        q = text.strip() or None
        self._refresh(search_query=q)

    def _on_clear_all(self):
        reply = QMessageBox.warning(
            self, "确认清空",
            "将清空所有剪贴板历史记录（包括图片缓存文件）。\n确定继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.db_manager.clear_all()
                self._refresh()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空失败: {e}")

    # ─── 键盘事件 ────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_panel()
        else:
            super().keyPressEvent(event)

    # ─── 失焦自动隐藏 ────────────────────────────────

    def focusOutEvent(self, event):
        # 延迟检查，避免弹出菜单导致的误隐藏
        QTimer.singleShot(150, self._check_hide)
        super().focusOutEvent(event)

    def _check_hide(self):
        if not self.isActiveWindow() and \
           not self.search_input.hasFocus():
            popup = QApplication.activePopupWidget()
            if popup is None:
                self.hide_panel()
