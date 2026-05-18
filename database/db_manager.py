"""
Clipboard_Master — 数据库管理器
负责 SQLite 建表、文本/图片记录的 CRUD、去重以及图片缓存文件管理。
"""
import os
import hashlib
import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional


class DatabaseManager:
    """
    剪贴板历史数据库管理器

    文本记录：内容直接存入 SQLite 的 content 字段。
    图片记录：QImage 保存为 PNG 文件到 cache/ 目录，
             文件路径存入 file_path 字段，缩略图路径存入 thumb_path 字段。
    """

    def __init__(self, db_path: str = "clipboard_history.db",
                 cache_dir: str = "cache"):
        self.db_path = db_path
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._init_db()

    # ─── 数据库初始化 ──────────────────────────────────

    def _init_db(self):
        """建表并创建索引"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type TEXT    NOT NULL CHECK(content_type IN ('text','image')),
                    content      TEXT,             -- 文本内容（text 类型专用）
                    file_path    TEXT,             -- 原图路径（image 类型专用）
                    thumb_path   TEXT,             -- 缩略图路径
                    content_hash TEXT    NOT NULL, -- MD5 去重哈希
                    source_app   TEXT,             -- 复制来源窗口标题
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hash
                    ON history(content_hash)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created
                    ON history(created_at DESC)
            """)
            conn.commit()

    # ─── 哈希 / 去重 ──────────────────────────────────

    @staticmethod
    def _compute_hash(data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    def _is_duplicate(self, content_hash: str) -> bool:
        """全表范围内检查是否已存在相同哈希的记录"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM history WHERE content_hash = ?",
                (content_hash,)
            )
            count = cursor.fetchone()[0]
            return count > 0

    # ─── 添加文本 ─────────────────────────────────────

    def add_text(self, text: str, source_app: str = None) -> Optional[int]:
        """
        添加文本记录，返回自增 ID；若内容为空或重复则返回 None。
        """
        text = text.strip()
        if not text:
            return None

        content_hash = self._compute_hash(text.encode('utf-8'))
        if self._is_duplicate(content_hash):
            return None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO history (content_type, content, content_hash, source_app)
                   VALUES (?, ?, ?, ?)""",
                ('text', text, content_hash, source_app)
            )
            conn.commit()
            return cursor.lastrowid

    # ─── 添加图片 ─────────────────────────────────────

    def add_image(self, qimage, source_app: str = None) -> Optional[int]:
        """
        将 QImage 保存为 PNG 并生成缩略图后写入数据库。
        返回自增 ID；若为空或重复则返回 None。
        """
        # QImage 判空
        if qimage is None or getattr(qimage, 'isNull', lambda: True)():
            return None

        # 将 QImage 像素数据取出用于 MD5 计算
        ba = qimage.bits()
        if ba is None:
            return None
        ba.setsize(qimage.byteCount())
        # ★ 修复：sip.voidptr 不支持 bytes()，必须用 .asstring() 读取底层内存
        raw_data = ba.asstring(qimage.byteCount())
        content_hash = self._compute_hash(raw_data)

        if self._is_duplicate(content_hash):
            return None

        # 生成唯一文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"clip_{timestamp}.png"
        file_path = os.path.join(self.cache_dir, filename)

        # 保存原图
        if not qimage.save(file_path, "PNG"):
            return None

        # 生成缩略图
        thumb_path = self._generate_thumbnail(file_path, timestamp)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO history
                   (content_type, file_path, thumb_path, content_hash, source_app)
                   VALUES (?, ?, ?, ?, ?)""",
                ('image', file_path, thumb_path, content_hash, source_app)
            )
            conn.commit()
            return cursor.lastrowid

    def _generate_thumbnail(self, image_path: str, timestamp: str,
                            size: tuple = (240, 180)) -> str:
        """
        使用 Pillow 生成缩略图；若无 Pillow 则回退到原图路径
        （UI 层会用 QPixmap.scaled 自行缩放）。
        """
        try:
            from PIL import Image
            img = Image.open(image_path)
            img.thumbnail(size, Image.LANCZOS)
            thumb_filename = f"thumb_{timestamp}.png"
            thumb_path = os.path.join(self.cache_dir, thumb_filename)
            img.save(thumb_path, "PNG")
            return thumb_path
        except ImportError:
            return image_path
        except Exception:
            return image_path

    # ─── 查询 ─────────────────────────────────────────

    def get_records(self, limit: int = 100, offset: int = 0,
                    content_type: str = None,
                    search_query: str = None) -> List[Tuple]:
        """
        分页获取记录。
        支持按 content_type 过滤、按文本模糊搜索。
        返回字段顺序: (id, content_type, content, file_path,
                       thumb_path, source_app, created_at)
        """
        query = """SELECT id, content_type, content, file_path,
                          thumb_path, source_app, created_at
                   FROM history WHERE 1=1"""
        params = []

        if content_type:
            query += " AND content_type = ?"
            params.append(content_type)
        if search_query:
            query += " AND content LIKE ?"
            params.append(f"%{search_query}%")

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()

    # ─── 删除 ─────────────────────────────────────────

    def delete_record(self, record_id: int):
        """
        删除指定记录；若为图片类型，同时清理磁盘上的缓存文件。
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT content_type, file_path, thumb_path "
                "FROM history WHERE id = ?",
                (record_id,)
            )
            row = cursor.fetchone()
            if row:
                content_type, file_path, thumb_path = row
                if content_type == 'image':
                    for path in (file_path, thumb_path):
                        if path and os.path.exists(path):
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
                conn.commit()

    def clear_all(self):
        """
        清空全部记录；同时清空 cache/ 目录下的所有文件。
        """
        # 删除磁盘缓存
        if os.path.exists(self.cache_dir):
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except OSError:
                    pass

        # 清空表
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM history")
            conn.commit()

    def get_record_count(self) -> int:
        """获取当前总记录数"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM history")
            return cursor.fetchone()[0]
