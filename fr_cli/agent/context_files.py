"""
Context Files 系统 - 参考 Hermes Agent 实现
项目上下文文件，塑造每次对话
"""

import os
import glob
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ContextFile:
    """上下文文件"""
    path: str
    content: str = ""
    size: int = 0
    loaded: bool = False

    def load_content(self):
        """加载文件内容"""
        if not self.loaded and os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self.content = f.read(100000)  # 限制 100KB
                    self.size = len(self.content)
                    self.loaded = True
            except Exception:
                pass


class ContextFilesManager:
    """上下文文件管理器"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.fr_cli")
        self.config_dir = config_dir
        self.context_file = os.path.join(config_dir, "context_files.json")
        self.patterns: List[str] = []
        self.exclude_patterns: List[str] = [".git/*", "node_modules/*", "__pycache__/*"]
        self._load_config()

    def _load_config(self):
        """加载配置"""
        if os.path.exists(self.context_file):
            try:
                import json
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.patterns = data.get("patterns", [])
                    self.exclude_patterns = data.get("exclude", self.exclude_patterns)
            except Exception:
                pass

    def _save_config(self):
        """保存配置"""
        import json
        os.makedirs(os.path.dirname(self.context_file), exist_ok=True)
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump({
                "patterns": self.patterns,
                "exclude": self.exclude_patterns
            }, f, indent=2)

    def add_pattern(self, pattern: str):
        """添加匹配模式"""
        if pattern not in self.patterns:
            self.patterns.append(pattern)
            self._save_config()

    def remove_pattern(self, pattern: str):
        """移除匹配模式"""
        if pattern in self.patterns:
            self.patterns.remove(pattern)
            self._save_config()

    def add_exclude(self, pattern: str):
        """添加排除模式"""
        if pattern not in self.exclude_patterns:
            self.exclude_patterns.append(pattern)
            self._save_config()

    def get_matching_files(self, root_dir: str = ".") -> List[str]:
        """获取匹配的文件列表"""
        files = set()

        for pattern in self.patterns:
            full_pattern = os.path.join(root_dir, pattern)
            matched = glob.glob(full_pattern, recursive=True)
            files.update(matched)

        # 应用排除
        excluded = set()
        for exclude in self.exclude_patterns:
            full_exclude = os.path.join(root_dir, exclude)
            matched = glob.glob(full_exclude, recursive=True)
            excluded.update(matched)

        return [f for f in files if f not in excluded]

    def load_context_files(self, root_dir: str = ".") -> List[ContextFile]:
        """加载所有上下文文件"""
        files = self.get_matching_files(root_dir)
        context_files = []

        for filepath in files:
            cf = ContextFile(path=filepath)
            cf.load_content()
            if cf.loaded:
                context_files.append(cf)

        return context_files

    def build_context_prompt(self, root_dir: str = ".") -> str:
        """构建上下文提示"""
        context_files = self.load_context_files(root_dir)
        if not context_files:
            return ""

        parts = ["\n\n# 项目上下文\n"]

        for cf in context_files:
            parts.append(f"\n## {os.path.relpath(cf.path, root_dir)}")
            parts.append(f"```\n{cf.content}\n```")

        return "\n".join(parts)

    def list_patterns(self) -> Dict:
        """列出所有模式"""
        return {
            "include": self.patterns,
            "exclude": self.exclude_patterns
        }

    def set_patterns(self, patterns: List[str]):
        """设置包含模式"""
        self.patterns = patterns
        self._save_config()

    def set_exclude_patterns(self, patterns: List[str]):
        """设置排除模式"""
        self.exclude_patterns = patterns
        self._save_config()


# 全局实例
_context_manager = None

def get_context_manager() -> ContextFilesManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextFilesManager()
    return _context_manager


def build_project_context(root_dir: str = ".") -> str:
    """构建项目上下文"""
    return get_context_manager().build_context_prompt(root_dir)