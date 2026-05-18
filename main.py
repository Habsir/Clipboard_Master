"""
Clipboard_Master — 程序入口

架构概览：
  ┌─────────────┐    ┌──────────────────┐    ┌────────────────┐
  │ System Tray │◄──►│ ClipboardMonitor │───►│ DatabaseManager│
  └──────┬──────┘    │ (QClipboard)     │    │ (SQLite+cache) │
         │           └──────────────────┘    └────────────────┘
  ┌──────▼──────┐          ┌──────────────────────┐
  │GlobalHotkey │─(子线程)─►│ hotkey_activated     │
   │(可自定义)    │  emit()  │ (pyqtSignal ─ 主线程) │
  └─────────────┘          └──────┬───────────────┘
                                  │ queued connection
                         ┌────────▼────────┐
                         │ _toggle_panel() │──► show_at(cursor_pos)
                         └─────────────────┘
  ┌──────────────────┐
  │  HistoryPanel    │  弹出式无边框窗口，网格瀑布流展示
  └──────────────────┘

线程安全设计：
  - keyboard 库热键回调运行在子线程，只调用 signal.emit()（线程安全）
  - PyQt 检测到跨线程 emit → 自动使用 Qt.QueuedConnection
  - _toggle_panel() 槽函数保证在主线程执行，安全操作 UI
"""
import sys
import os
import json
import hashlib

# 确保项目根目录在 sys.path 中，以便 ui/ database/ 子包可被导入
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QGuiApplication, QCursor
from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog

from database.db_manager import DatabaseManager
from ui.tray_icon import TrayIcon
from ui.history_panel import HistoryPanel
from ui.hotkey_dialog import HotkeyDialog


# ─── 配置持久化 ───────────────────────────────────────

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
DEFAULT_HOTKEY = 'ctrl+shift+c'


def _load_config() -> dict:
    """加载配置文件，不存在则返回默认值"""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {"hotkey": DEFAULT_HOTKEY}


def _save_config(config: dict):
    """保存配置到文件"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Config] 保存失败: {e}")


# ─── 剪贴板监听器 ─────────────────────────────────────

class ClipboardMonitor(QObject):
    """
    监听系统剪贴板变化（文本 & 图片），写入数据库。

    通过 QClipboard.dataChanged 信号触发；
    使用 MD5 哈希去重 + 防抖机制，避免重复入/频繁写入。
    """

    # 去抖间隔（毫秒）
    DEBOUNCE_MS = 300

    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self._enabled = True
        self._last_hash = None
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._check_clipboard)

        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_change)

    def _on_clipboard_change(self):
        """剪贴板变化 → 启动去抖定时器"""
        if not self._enabled:
            return
        self._debounce_timer.start(self.DEBOUNCE_MS)

    def _check_clipboard(self):
        """去抖后执行：读取剪贴板内容并存储"""
        clipboard = QApplication.clipboard()

        # 1) 尝试读取图片
        image = clipboard.image()
        if image and not getattr(image, 'isNull', lambda: True)():
            # 计算哈希防重复
            ba = image.bits()
            if ba is not None:
                ba.setsize(image.byteCount())
                # ★ 修复：sip.voidptr 不支持 bytes()，必须用 .asstring() 读取底层内存
                img_hash = hashlib.md5(ba.asstring(image.byteCount())).hexdigest()
                if img_hash != self._last_hash:
                    self._last_hash = img_hash
                    source = self._get_foreground_title()
                    self.db.add_image(image, source_app=source)
            return

        # 2) 尝试读取文本
        text = clipboard.text()
        if text and text.strip():
            text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            if text_hash != self._last_hash:
                self._last_hash = text_hash
                source = self._get_foreground_title()
                self.db.add_text(text, source_app=source)

    @staticmethod
    def _get_foreground_title() -> str:
        """获取当前前台窗口标题（Windows 专用，跨平台回退）"""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or "未知窗口"
        except Exception:
            return None

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def force_check(self):
        """
        强制立即检查剪贴板（绕过 300ms 防抖定时器）。

        调用时机：用户按热键打开面板时，
        确保最新复制的内存在 _refresh() 查询数据库前已写入。
        """
        if not self._enabled:
            return
        self._debounce_timer.stop()
        self._check_clipboard()


# ─── 全局热键管理器 ───────────────────────────────────

class HotkeyManager:
    """
    全局热键注册（基于 keyboard 库）。

    线程安全设计：
      - keyboard.add_hotkey 回调在子线程执行
      - callback 参数应传入 pyqtSignal.emit（线程安全）
      - 调用方通过 Qt.QueuedConnection 将 UI 操作自动调度到主线程

    支持运行时动态切换热键。
    """

    # 默认热键
    DEFAULT_HOTKEY = 'ctrl+shift+c'

    def __init__(self, callback):
        """
        callback: 无参数可调用对象（推荐传入 pyqtSignal.emit）
        """
        self._callback = callback
        self._active = False
        self._current_hotkey = self.DEFAULT_HOTKEY

    @property
    def current_hotkey(self) -> str:
        return self._current_hotkey

    def register(self, hotkey: str = None):
        """
        注册全局热键。

        hotkey: keyboard 库兼容格式字符串，如 'ctrl+shift+c'。
                若为 None 则使用 self._current_hotkey。
        """
        if hotkey is not None:
            self._current_hotkey = hotkey

        try:
            import keyboard

            # 主热键
            keyboard.add_hotkey(self._current_hotkey, self._callback)
            print(f"[Hotkey] 已注册 {self._current_hotkey}")

            # 辅热键：Win+C（尝试注册，系统可能拦截）
            try:
                keyboard.add_hotkey('win+c', self._callback)
                print("[Hotkey] 已注册 Win+C（备用）")
            except Exception as e:
                print(f"[Hotkey] Win+C 注册失败 (系统可能占用): {e}")

            self._active = True

        except ImportError:
            print("[Hotkey] keyboard 库未安装！")
            print("  请运行: pip install keyboard")
            print("  将以系统托盘菜单作为替代唤醒方式。")
        except Exception as e:
            print(f"[Hotkey] 注册失败: {e}")

    def change_hotkey(self, new_hotkey: str):
        """
        运行时切换热键：先注销旧热键，再注册新热键。

        若新热键与旧热键相同，不执行任何操作。
        返回 True 表示切换成功。
        """
        if new_hotkey == self._current_hotkey:
            return True

        # 1) 注销旧热键
        self.unregister()

        # 2) 注册新热键
        self._current_hotkey = new_hotkey
        try:
            import keyboard
            keyboard.add_hotkey(self._current_hotkey, self._callback)
            keyboard.add_hotkey('win+c', self._callback)  # 备用保持不变
            self._active = True
            print(f"[Hotkey] 已切换至 {self._current_hotkey}")
            return True
        except Exception as e:
            print(f"[Hotkey] 切换失败: {e}")
            return False

    def unregister(self):
        """注销所有热键"""
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        self._active = False


# ─── 主应用程序 ────────────────────────────────────────

class ClipboardMasterApp(QObject):
    """
    应用程序主控制器（QObject 以支持 pyqtSignal），
    负责各组件生命周期管理。

    线程安全架构：
      HotkeyManager（子线程）──emit──► hotkey_activated（信号）
                                             │ Qt.QueuedConnection
                                             ▼
                                      _toggle_panel()（主线程槽函数）
    """

    # ★ 跨线程信号：子线程只 emit，主线程槽函数安全操作 UI
    hotkey_activated = pyqtSignal()

    def __init__(self):
        super().__init__()

        # ── 加载配置 ──
        self._config = _load_config()
        saved_hotkey = self._config.get("hotkey", DEFAULT_HOTKEY)

        self.db = DatabaseManager(
            db_path=os.path.join(PROJECT_ROOT, "clipboard_history.db"),
            cache_dir=os.path.join(PROJECT_ROOT, "cache")
        )
        self.tray = TrayIcon()
        self.panel = HistoryPanel(self.db)
        self.monitor = ClipboardMonitor(self.db)
        # ★ HotkeyManager 回调指向 signal.emit（线程安全）
        self.hotkey = HotkeyManager(self.hotkey_activated.emit)

        # 使用保存的热键
        self.hotkey._current_hotkey = saved_hotkey
        self.tray.set_hotkey(saved_hotkey)

        self._connect_signals()

    def _connect_signals(self):
        """连接各组件信号（全部在主线程执行）"""
        # ★ 热键线程安全桥接：子线程 emit → 主线程槽函数
        self.hotkey_activated.connect(self._toggle_panel)

        # 托盘菜单
        self.tray.show_panel_requested.connect(self._toggle_panel)
        self.tray.clear_requested.connect(self._clear_history)
        self.tray.quit_requested.connect(self._quit)
        self.tray.monitoring_toggled.connect(self.monitor.set_enabled)
        self.tray.hotkey_change_requested.connect(self._on_change_hotkey)

        # 面板关闭 → 失焦后自动清理
        self.panel.panel_closed.connect(lambda: None)  # 预留扩展

    # ─── 核心操作 ────────────────────────────────────

    def _toggle_panel(self):
        """
        切换面板显示/隐藏（槽函数，保证在主线程执行）

        由 hotkey_activated 信号（跨线程桥接）或托盘菜单触发。
        打开面板前强制立即检查剪贴板，绕过 300ms 防抖定时器，
        确保最新复制的内容在面板查询数据库前已被写入。
        """
        if self.panel.is_visible():
            self.panel.hide_panel()
        else:
            # ★ 关键：打开面板前立即读取剪贴板，避免防抖延迟导致面板显示空数据
            self.monitor.force_check()
            cursor_pos = QCursor.pos()
            self.panel.show_at(cursor_pos)

    def _clear_history(self):
        """清空全部历史"""
        reply = QMessageBox.question(
            None, "确认清空",
            "确定要清空所有剪贴板历史记录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.db.clear_all()

    def _quit(self):
        """退出程序"""
        self.hotkey.unregister()
        self.tray.hide()
        QApplication.quit()

    def _on_change_hotkey(self):
        """
        打开热键录制对话框，用户确认后切换全局热键并保存配置。

        流程:
          1. 弹出 HotkeyDialog（显示当前热键）
          2. 用户按下新组合键 → 录制 → 点确认
          3. 调用 HotkeyManager.change_hotkey() 切换
          4. 更新托盘提示文字
          5. 保存到 config.json
        """
        dialog = HotkeyDialog(self.hotkey.current_hotkey)
        if dialog.exec_() == QDialog.Accepted:
            new_hotkey = dialog.hotkey_string
            if self.hotkey.change_hotkey(new_hotkey):
                self.tray.set_hotkey(new_hotkey)
                # 持久化保存
                self._config["hotkey"] = new_hotkey
                _save_config(self._config)
                self.tray.notify(
                    "热键已更改",
                    f"新热键: {new_hotkey}"
                )

    def run(self):
        """启动应用程序"""
        # 显示托盘图标
        self.tray.show()

        # 欢迎提示（使用当前热键）
        self.tray.notify(
            "Clipboard Master",
            "剪贴板历史管理已启动\n"
            f"按 {self.hotkey.current_hotkey} 唤醒历史面板\n"
            "面板中按住卡片可拖拽到桌面导出文件"
        )

        # 注册全局热键
        self.hotkey.register()
        if not self.hotkey._active:
            self.tray.notify(
                "⚠ 热键提示",
                "全局热键注册失败\n"
                "请通过托盘菜单唤醒面板"
            )


# ─── 入口 ─────────────────────────────────────────────

def main():
    # 高 DPI 适配
    QGuiApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Clipboard Master")
    app.setQuitOnLastWindowClosed(False)  # 关闭面板不退出程序

    master = ClipboardMasterApp()
    master.run()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
