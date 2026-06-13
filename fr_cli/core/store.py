"""
统一 JSON 持久化抽象 —— JsonStore

将散落在各模块中的 JSON 读写收敛为单一实现，提供：
- 原子写（先写 .tmp 再 replace，避免写一半崩溃丢数据）
- 文件权限控制（默认 0o600）
- 线程安全（RLock）
- 默认值工厂
- 异常安全（读取失败返回默认值，不抛异常）
"""
import json
import os
import threading
from pathlib import Path


class JsonStore:
    """基于 JSON 文件的键值持久化存储"""

    def __init__(self, path, default=None, chmod=0o600):
        """
        :param path: 持久化文件路径（字符串或 Path）
        :param default: 文件不存在或读取失败时返回的默认值；可为工厂函数
        :param chmod: 文件权限，None 表示不修改
        """
        self.path = Path(path)
        if callable(default):
            self._default_factory = default
        elif default is not None:
            self._default_factory = lambda: default
        else:
            self._default_factory = dict
        self.chmod = chmod
        self._lock = threading.RLock()

    def read(self):
        """读取 JSON 文件；不存在或失败则返回默认值副本"""
        with self._lock:
            if not self.path.exists():
                return self._default_factory()
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return self._default_factory()

    def write(self, data):
        """原子写入 JSON 文件；写入失败静默忽略"""
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                tmp.replace(self.path)
                if self.chmod is not None:
                    try:
                        os.chmod(self.path, self.chmod)
                    except Exception:
                        pass
            except Exception:
                pass

    def exists(self):
        """判断文件是否存在"""
        return self.path.exists()

    def delete(self):
        """删除持久化文件（若存在）"""
        with self._lock:
            if self.path.exists():
                try:
                    self.path.unlink()
                except Exception:
                    pass
