# Clipboard Master（剪贴板历史管理器）

> 轻量级 Windows 剪贴板历史管理器 — 常驻系统托盘，全局热键唤醒，拖拽一键导出。

## 功能

- **剪贴板历史记录** — 自动监听文本和图片复制，MD5 去重防重复
- **全局热键唤醒** — 默认 `Ctrl+Shift+C`，可在托盘菜单中自定义
- **网格瀑布流面板** — 无边框弹出窗口，搜索过滤，失焦/ESC 自动隐藏
- **拖拽导出** — 按住卡片拖拽到桌面或文件夹，自动生成 `.txt` / `.png` 文件
- **右键菜单** — 重新复制到剪贴板、打开文件位置、删除单条记录
- **图片缩略图** — Pillow 生成缩略图加速浏览，无 Pillow 时回退 QPixmap 缩放
- **暂停/恢复监听** — 临时关闭剪贴板监控，保护隐私
- **一键清空** — 清空所有历史及磁盘缓存文件

## 界面

```
┌─────────────────────────────────────┐
│ 📋 剪贴板历史         共 12 条  ✕  │
│ 🔍 搜索历史记录…                   │
│ ┌─────────┐ ┌─────────┐ ┌────────┐ │
│ │ 文本预览 │ │ 文本预览 │ │ 🖼 图片 │ │
│ │         │ │         │ │ 缩略图  │ │
│ │  11:23  │ │  11:20  │ │  11:18  │ │
│ └─────────┘ └─────────┘ └────────┘ │
│ ┌─────────┐ ┌─────────┐            │
│ │ 文本预览 │ │ 文本预览 │            │
│ │  11:15  │ │  11:10  │            │
│ └─────────┘ └─────────┘            │
└─────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.8+
- 以管理员身份运行（全局热键需要）

### 从源码运行

```powershell
# 1. 克隆仓库
git clone https://github.com/Habsir/Clipboard_Master.git
cd Clipboard_Master

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python main.py
```

程序启动后驻留系统托盘（蓝色剪贴板图标），按 `Ctrl+Shift+C` 唤醒历史面板。

### 使用打包好的 EXE

下载 [Releases](https://github.com/Habsir/Clipboard_Master/releases) 中的 `ClipboardMaster.exe`，双击运行即可，无需安装 Python 环境。

## 使用方法

| 操作 | 方式 |
|------|------|
| 唤醒面板 | `Ctrl+Shift+C`（默认）或单击托盘图标 |
| 关闭面板 | 点击 ✕ / 按 `Esc` / 点击面板外区域 |
| 搜索记录 | 在搜索框输入关键词，实时过滤 |
| 拖拽导出 | 按住卡片拖到桌面或文件夹 |
| 重新复制 | 右键卡片 →「📋 重新复制」 |
| 删除记录 | 右键卡片 →「🗑 删除此记录」 |
| 清空全部 | 面板「清空全部」或托盘右键「🗑 清空历史」 |
| 暂停监听 | 托盘右键 →「⏸ 暂停监听」 |
| 更改热键 | 托盘右键 →「⌨ 更改热键…」→ 按下新组合键确认 |

## 自定义热键

点击托盘菜单「⌨ 更改热键…」，在弹出的对话框中按下新的组合键（如 `Ctrl+Alt+V`），确认后即时生效，并自动保存到 `config.json`，下次启动无需重新设置。

支持的热键格式：`Ctrl / Shift / Alt / Win` + 字母/数字/功能键。

## 项目结构

```
Clipboard_Master/
├── main.py                  # 入口 & 主控制器（信号-槽桥接）
├── requirements.txt         # 依赖清单
├── .gitignore               # Git 忽略规则
├── README.md                # 项目说明
├── database/
│   ├── __init__.py
│   └── db_manager.py        # SQLite CRUD + MD5去重 + Pillow缩略图
└── ui/
    ├── __init__.py
    ├── tray_icon.py         # 系统托盘（QPainter 绘制图标 + 右键菜单）
    ├── history_panel.py     # 弹出面板（无边框、网格瀑布流、搜索、失焦隐藏）
    ├── list_item.py          # 卡片组件（文本/图片预览 + 拖拽导出）
    └── hotkey_dialog.py     # 热键录制对话框（按键捕获 → 持久化配置）
```

## 技术栈

| 组件 | 技术 |
|------|------|
| GUI 框架 | PyQt5 |
| 全局热键 | keyboard |
| 图片处理 | Pillow（可选回退） |
| 数据存储 | SQLite |
| 打包工具 | PyInstaller |

## 从源码打包

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name "ClipboardMaster" main.py
```

生成的 EXE 位于 `dist/ClipboardMaster.exe`。

## 许可

MIT License
