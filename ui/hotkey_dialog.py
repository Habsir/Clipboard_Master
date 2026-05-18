"""
Clipboard_Master — 热键录制对话框

按下组合键（如 Ctrl+Shift+C）即可录制新热键，
确认后返回 keyboard 库兼容格式字符串。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame)


# ─── Qt 键码 → keyboard 库键名映射 ─────────────────────

# 修饰键
_MODIFIER_MAP = {
    Qt.Key_Control: 'ctrl',
    Qt.Key_Shift:   'shift',
    Qt.Key_Alt:     'alt',
    Qt.Key_Meta:    'win',
}

# 普通字母/数字键
_LETTER_DIGIT = set(range(Qt.Key_A, Qt.Key_Z + 1)) | \
                set(range(Qt.Key_0, Qt.Key_9 + 1))

# 特殊功能键 → keyboard 库键名
_SPECIAL_KEY_MAP = {
    Qt.Key_F1:  'f1',   Qt.Key_F2:  'f2',   Qt.Key_F3:  'f3',
    Qt.Key_F4:  'f4',   Qt.Key_F5:  'f5',   Qt.Key_F6:  'f6',
    Qt.Key_F7:  'f7',   Qt.Key_F8:  'f8',   Qt.Key_F9:  'f9',
    Qt.Key_F10: 'f10',  Qt.Key_F11: 'f11',  Qt.Key_F12: 'f12',
    Qt.Key_Space:      'space',
    Qt.Key_Return:     'enter',
    Qt.Key_Enter:      'enter',
    Qt.Key_Tab:        'tab',
    Qt.Key_Backspace:  'backspace',
    Qt.Key_Delete:     'delete',
    Qt.Key_Escape:     'esc',
    Qt.Key_Home:       'home',
    Qt.Key_End:        'end',
    Qt.Key_PageUp:     'page up',
    Qt.Key_PageDown:   'page down',
    Qt.Key_Insert:     'insert',
    Qt.Key_Print:      'print screen',
    Qt.Key_Up:         'up',
    Qt.Key_Down:       'down',
    Qt.Key_Left:       'left',
    Qt.Key_Right:      'right',
    Qt.Key_Plus:       '+',
    Qt.Key_Minus:      '-',
    Qt.Key_Comma:      ',',
    Qt.Key_Period:     '.',
    Qt.Key_Slash:      '/',
    Qt.Key_Semicolon:  ';',
    Qt.Key_QuoteLeft:  '`',
    Qt.Key_BracketLeft:  '[',
    Qt.Key_BracketRight: ']',
    Qt.Key_Backslash:  '\\',
}

# ─── 热键录制对话框 ────────────────────────────────────

class HotkeyDialog(QDialog):
    """
    热键录制对话框 — 按下组合键即录制。

    用法:
        dialog = HotkeyDialog("ctrl+shift+c", parent)
        if dialog.exec_() == QDialog.Accepted:
            new_hotkey = dialog.hotkey_string  # "ctrl+shift+c"
    """

    def __init__(self, current_hotkey: str, parent=None):
        super().__init__(parent)
        self._current_hotkey = current_hotkey
        self._modifiers: set = set()   # 当前按下的修饰键集合
        self._pressed_key: str = ""    # 当前按下的非修饰键名
        self._recorded: str = ""       # 最终录制的完整热键字符串

        self._init_ui()
        self._apply_styles()

    @property
    def hotkey_string(self) -> str:
        """返回录制的热键字符串（keyboard 库格式）"""
        return self._recorded or self._current_hotkey

    # ─── UI ────────────────────────────────────────────

    def _init_ui(self):
        self.setWindowTitle("更改全局热键")
        self.setFixedSize(380, 240)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── 提示文字 ──
        hint = QLabel("请按下新的组合键（例如 Ctrl+Shift+D）")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #555; font-size: 13px;")
        layout.addWidget(hint)

        # ── 当前热键显示 ──
        current_label = QLabel(f"当前热键：{self._current_hotkey}")
        current_label.setAlignment(Qt.AlignCenter)
        current_label.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(current_label)

        # ── 录制显示区域 ──
        self._record_frame = QFrame()
        self._record_frame.setObjectName("recordFrame")
        self._record_frame.setFixedHeight(52)
        record_layout = QVBoxLayout(self._record_frame)
        record_layout.setContentsMargins(0, 0, 0, 0)

        self._record_label = QLabel("等待按键…")
        self._record_label.setAlignment(Qt.AlignCenter)
        self._record_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #4a90d9;"
        )
        record_layout.addWidget(self._record_label)

        layout.addWidget(self._record_frame)

        # ── 提示：至少需要一个修饰键 + 一个普通键 ──
        self._tip_label = QLabel(
            "至少需要 Ctrl / Shift / Alt / Win + 一个普通键"
        )
        self._tip_label.setAlignment(Qt.AlignCenter)
        self._tip_label.setStyleSheet("color: #bbb; font-size: 11px;")
        layout.addWidget(self._tip_label)

        layout.addStretch()

        # ── 按钮行 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self._ok_btn = QPushButton("确认")
        self._ok_btn.setObjectName("okBtn")
        self._ok_btn.setFixedSize(80, 32)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self._ok_btn)

        layout.addLayout(btn_layout)

        # ── 安装事件过滤器以捕获所有按键 ──
        self.installEventFilter(self)

    def _apply_styles(self):
        self.setStyleSheet("""
            HotkeyDialog {
                background: #ffffff;
            }
            #recordFrame {
                background: #f0f4ff;
                border: 2px dashed #4a90d9;
                border-radius: 10px;
            }
            #okBtn {
                background: #4a90d9;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
            }
            #okBtn:hover { background: #357abd; }
            #okBtn:disabled { background: #c0c0c0; }
            #cancelBtn {
                background: #f0f0f0;
                color: #555;
                border: none;
                border-radius: 16px;
                font-size: 13px;
            }
            #cancelBtn:hover { background: #e0e0e0; }
        """)

    # ─── 事件过滤器：录制按键 ──────────────────────────

    def eventFilter(self, obj, event):
        """拦截所有按键事件，实现热键录制"""
        if event.type() == event.KeyPress:
            self._handle_key_press(event)
            return True  # 消费事件，避免默认处理
        elif event.type() == event.KeyRelease:
            self._handle_key_release(event)
            return True
        return super().eventFilter(obj, event)

    def _handle_key_press(self, event: QKeyEvent):
        key = event.key()

        # ★ 忽略单独的修饰键按下
        if key in _MODIFIER_MAP:
            self._modifiers.add(key)
            return

        # 自动捕获 Qt 原生修饰键状态（确保跨平台准确性）
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            self._modifiers.add(Qt.Key_Control)
        if modifiers & Qt.ShiftModifier:
            self._modifiers.add(Qt.Key_Shift)
        if modifiers & Qt.AltModifier:
            self._modifiers.add(Qt.Key_Alt)
        if modifiers & Qt.MetaModifier:
            self._modifiers.add(Qt.Key_Meta)

        # 将键码转换为键名
        key_name = self._key_to_name(key)
        if key_name is None:
            return  # 不支持的键，忽略

        self._pressed_key = key_name
        self._update_display()

    def _handle_key_release(self, event: QKeyEvent):
        key = event.key()
        if key in _MODIFIER_MAP:
            self._modifiers.discard(key)

    def _key_to_name(self, key: int) -> str or None:
        """Qt 键码 → keyboard 库兼容键名；不支持则返回 None"""
        # 字母键
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key).lower()
        # 数字键
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)
        # 特殊键
        if key in _SPECIAL_KEY_MAP:
            return _SPECIAL_KEY_MAP[key]
        return None

    def _update_display(self):
        """更新录制显示并验证是否有效"""
        if not self._modifiers or not self._pressed_key:
            return

        # 修饰键按固定顺序排序: ctrl > shift > alt > win
        mod_order = {Qt.Key_Control: 0, Qt.Key_Shift: 1,
                     Qt.Key_Alt: 2, Qt.Key_Meta: 3}
        sorted_mods = sorted(self._modifiers,
                             key=lambda k: mod_order.get(k, 99))
        mod_names = [_MODIFIER_MAP[k] for k in sorted_mods]

        hotkey = '+'.join(mod_names + [self._pressed_key])

        self._recorded = hotkey
        self._record_label.setText(hotkey)
        self._record_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #27ae60;"
        )
        self._tip_label.setText("✓ 已录制，点击「确认」保存")
        self._tip_label.setStyleSheet("color: #27ae60; font-size: 11px;")
        self._ok_btn.setEnabled(True)

    def _on_confirm(self):
        """确认按钮回调"""
        if self._recorded:
            self.accept()
