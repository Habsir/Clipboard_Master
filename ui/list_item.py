"""
Clipboard_Master — 历史记录列表项组件

核心功能：
- 文本预览（截断显示） / 图片缩略图
- 【核心】鼠标拖拽导出：按住拖拽到桌面/文件夹自动生成实体文件
- 右键菜单：重新复制、打开文件位置、删除记录
"""
import os
import shutil
import tempfile
import threading
from datetime import datetime

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPixmap, QDrag, QCursor
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QLabel, QApplication,
                              QMenu, QAction, QMessageBox)


class ListItemWidget(QFrame):
    """
    可拖拽的历史记录卡片

    拖拽实现逻辑（系统级文件拖拽）：
      1. mousePressEvent  记录起始坐标
      2. mouseMoveEvent   超过阈值 → 创建临时文件
      3. 构建 QMimeData.setUrls(temporary_file_path)
         └─ Windows Explorer 通过 CF_HDROP 格式识别此 URL
      4. QDrag.exec_(Qt.CopyAction) 执行拖拽
      5. 拖拽完成后延迟清理临时文件（避免 Explorer 仍在读取）
    """

    # ─── 卡片尺寸常量 ──
    ITEM_WIDTH = 200
    TEXT_ITEM_HEIGHT = 110
    IMAGE_ITEM_HEIGHT = 180

    def __init__(self, record_data: tuple, parent=None):
        """
        record_data 字段顺序（由 DatabaseManager.get_records 返回）：
          (id, content_type, content, file_path,
           thumb_path, source_app, created_at)
        """
        super().__init__(parent)

        (self.record_id, self.content_type, self.content,
         self.file_path, self.thumb_path, self.source_app,
         self.created_at) = record_data

        # 拖拽状态
        self._drag_start_pos: QPoint = None

        self._init_ui()

    # ─── UI 初始化 ────────────────────────────────────

    def _init_ui(self):
        """根据内容类型构建文本预览或图片缩略图"""
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("🖱 按住拖拽到桌面或文件夹即可导出文件\n"
                        "🖱 右键查看更多操作")

        height = (self.IMAGE_ITEM_HEIGHT if self.content_type == 'image'
                  else self.TEXT_ITEM_HEIGHT)
        self.setFixedSize(self.ITEM_WIDTH, height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # ── 主体内容区域 ──
        if self.content_type == 'image':
            self._build_image_preview(layout)
        else:
            self._build_text_preview(layout)

        # ── 底部信息栏：时间戳 ──
        bottom_row = QVBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        time_str = self._format_time()
        time_label = QLabel(time_str)
        time_label.setAlignment(Qt.AlignRight)
        time_label.setStyleSheet("color: #999; font-size: 9px;")
        time_label.setMaximumHeight(16)
        bottom_row.addWidget(time_label)

        layout.addLayout(bottom_row)

        # ── 默认样式 ──
        self._apply_style("normal")

    def _build_text_preview(self, layout: QVBoxLayout):
        """文本类型：截断预览"""
        text_label = QLabel(self)
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        text_label.setStyleSheet(
            "color: #333; font-size: 11px; padding: 6px;"
            "background: #f8f9fa; border-radius: 5px;"
        )

        # 最多显示 120 个字符
        MAX_CHARS = 120
        preview = self.content[:MAX_CHARS] if self.content else ""
        if len(self.content or "") > MAX_CHARS:
            preview += "…"
        text_label.setText(preview)

        layout.addWidget(text_label)

    def _build_image_preview(self, layout: QVBoxLayout):
        """图片类型：加载缩略图"""
        image_label = QLabel(self)
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet(
            "background: #e9ecef; border-radius: 5px;"
        )
        image_label.setScaledContents(False)

        # 优先使用缩略图，无缩略图则用原图缩放
        img_path = self.thumb_path or self.file_path
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                target_w = self.ITEM_WIDTH - 16
                target_h = self.IMAGE_ITEM_HEIGHT - 40
                scaled = pixmap.scaled(
                    target_w, target_h,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                image_label.setPixmap(scaled)
            else:
                image_label.setText("⚠ 图片损坏")
        else:
            image_label.setText("📷 无缓存")

        layout.addWidget(image_label)

    def _format_time(self) -> str:
        """时间戳 → HH:MM:SS"""
        try:
            if self.created_at:
                return self.created_at.split('.')[0][-8:]
        except Exception:
            pass
        return ""

    # ─── 样式管理 ─────────────────────────────────────

    def _apply_style(self, state: str):
        if state == "hover":
            self.setStyleSheet("""
                ListItemWidget {
                    border: 2px solid #4a90d9;
                    border-radius: 10px;
                    background: #ffffff;
                }
            """)
        else:
            self.setStyleSheet("""
                ListItemWidget {
                    border: 1px solid #e0e0e0;
                    border-radius: 10px;
                    background: #ffffff;
                }
            """)

    def enterEvent(self, event):
        self._apply_style("hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style("normal")
        super().leaveEvent(event)

    # ═══════════════════════════════════════════════════
    #  【核心】拖拽事件 — 系统级文件拖拽导出
    # ═══════════════════════════════════════════════════

    def mousePressEvent(self, event):
        """记录拖拽起始坐标"""
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        拖拽检测与执行：
        - 移动距离超过 QApplication.startDragDistance() 时触发
        - 先创建临时文件，再通过 QMimeData.setUrls 导出
        """
        if self._drag_start_pos is None:
            return

        # 距离检测（PyQt5 内置拖拽阈值）
        if (event.pos() - self._drag_start_pos).manhattanLength() < \
                QApplication.startDragDistance():
            return

        # ── 步骤 1：创建临时文件 ──
        temp_path = self._create_temp_file()
        if not temp_path:
            self._drag_start_pos = None
            self.setCursor(Qt.OpenHandCursor)
            return

        # ── 步骤 2：构建拖拽数据 ──
        from PyQt5.QtCore import QMimeData, QUrl
        mime_data = QMimeData()

        # ★ 关键：设置文件 URL（Windows Explorer 识别 CF_HDROP 格式）
        mime_data.setUrls([QUrl.fromLocalFile(temp_path)])

        # 附加纯文本（支持拖入文本编辑器）
        if self.content_type == 'text' and self.content:
            mime_data.setText(self.content)

        # ── 步骤 3：创建 QDrag 对象 ──
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setHotSpot(event.pos())

        # 拖拽缩略图
        grab_pixmap = self.grab()
        if not grab_pixmap.isNull():
            drag.setPixmap(
                grab_pixmap.scaled(100, 80, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            )

        # ── 步骤 4：执行拖拽 ──
        result = drag.exec_(Qt.CopyAction | Qt.MoveAction)

        # ── 步骤 5：延迟清理（Explorer 可能仍在读取文件） ──
        if result == Qt.CopyAction:
            threading.Timer(
                3.0,
                lambda p=temp_path: self._safe_remove(p)
            ).start()

        # 重置拖拽状态
        self._drag_start_pos = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        """释放鼠标 → 重置拖拽状态"""
        self._drag_start_pos = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def _create_temp_file(self) -> str:
        """
        在系统临时目录创建实体文件，供 Explorer 拖拽识别。

        文本 → .txt 文件
        图片 → .png 文件（复制自缓存目录）
        """
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

            if self.content_type == 'text' and self.content:
                # 截取安全文件名（前20个合法字符）
                safe = "".join(
                    c for c in self.content[:20]
                    if c.isalnum() or c in ' _-'
                ).strip() or "clipboard_text"
                filename = f"{safe}_{ts}.txt"
                temp_path = os.path.join(tempfile.gettempdir(), filename)

                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(self.content)
                return temp_path

            elif self.content_type == 'image' and self.file_path:
                if os.path.exists(self.file_path):
                    filename = f"clipboard_image_{ts}.png"
                    temp_path = os.path.join(tempfile.gettempdir(), filename)
                    shutil.copy2(self.file_path, temp_path)
                    return temp_path

        except Exception as e:
            print(f"[ListItemWidget] 临时文件创建失败: {e}")
        return None

    @staticmethod
    def _safe_remove(file_path: str):
        """忽略错误的文件删除"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass

    # ═══════════════════════════════════════════════════
    #  右键菜单
    # ═══════════════════════════════════════════════════

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #fff;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 7px 24px;
                border-radius: 5px;
            }
            QMenu::item:selected {
                background: #e3f2fd;
                color: #1976d2;
            }
            QMenu::separator {
                height: 1px;
                background: #eee;
                margin: 3px 8px;
            }
        """)

        # 重新复制到剪贴板
        copy_action = QAction("📋 重新复制", menu)
        copy_action.triggered.connect(self._re_copy)
        menu.addAction(copy_action)

        # 浏览文件位置（仅图片）
        if self.content_type == 'image' and self.file_path:
            open_action = QAction("📂 打开文件位置", menu)
            open_action.triggered.connect(self._open_file_location)
            menu.addAction(open_action)

        menu.addSeparator()

        # 删除
        del_action = QAction("🗑 删除此记录", menu)
        del_action.triggered.connect(self._confirm_delete)
        menu.addAction(del_action)

        menu.exec_(event.globalPos())

    def _re_copy(self):
        """将内容重新写入系统剪贴板"""
        clipboard = QApplication.clipboard()
        if self.content_type == 'text' and self.content:
            clipboard.setText(self.content)
        elif self.content_type == 'image' and self.file_path:
            pixmap = QPixmap(self.file_path)
            if not pixmap.isNull():
                clipboard.setPixmap(pixmap)

    def _open_file_location(self):
        """资源管理器打开文件所在目录"""
        if self.file_path and os.path.exists(self.file_path):
            os.startfile(os.path.dirname(self.file_path))

    def _confirm_delete(self):
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要永久删除这条记录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            #  向上查找 HistoryPanel 并调用删除方法
            parent = self.parent()
            while parent:
                if hasattr(parent, 'delete_record_by_id'):
                    parent.delete_record_by_id(self.record_id)
                    break
                parent = parent.parent()
