"""
Plugin 系统 - Hermes 插件支持
参考 hermes-agent 的 plugin 架构
"""

import os
import importlib
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass


@dataclass
class Plugin:
    """插件"""
    name: str
    version: str
    description: str
    author: str = "unknown"
    enabled: bool = True
    config: Dict = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}


class PluginRegistry:
    """插件注册表"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.plugins: Dict[str, Plugin] = {}
        self.hooks: Dict[str, List[Callable]] = {
            "on_startup": [],
            "on_shutdown": [],
            "on_message": [],
            "on_tool_call": [],
            "on_task_complete": []
        }
        self._load_plugins()

    def _load_plugins(self):
        """加载内置插件"""
        plugin_dir = os.path.join(os.path.dirname(__file__), "builtins")
        if os.path.exists(plugin_dir):
            for filename in os.listdir(plugin_dir):
                if filename.endswith(".py") and not filename.startswith("_"):
                    plugin_name = filename[:-3]
                    self._register_builtin_plugin(plugin_name)

    def _register_builtin_plugin(self, name: str):
        """注册内置插件"""
        self.register(Plugin(
            name=name,
            version="1.0.0",
            description=f"Built-in plugin: {name}",
            author="fr-cli"
        ))

    def register(self, plugin: Plugin):
        """注册插件"""
        self.plugins[plugin.name] = plugin

    def unregister(self, name: str) -> bool:
        """取消注册"""
        if name in self.plugins:
            del self.plugins[name]
            return True
        return False

    def get(self, name: str) -> Optional[Plugin]:
        """获取插件"""
        return self.plugins.get(name)

    def list_all(self) -> List[Plugin]:
        """列出所有插件"""
        return list(self.plugins.values())

    def enable(self, name: str):
        """启用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = True

    def disable(self, name: str):
        """禁用插件"""
        if name in self.plugins:
            self.plugins[name].enabled = False

    def register_hook(self, event: str, callback: Callable):
        """注册钩子"""
        if event in self.hooks:
            self.hooks[event].append(callback)

    def trigger_hook(self, event: str, *args, **kwargs):
        """触发钩子"""
        results = []
        for callback in self.hooks.get(event, []):
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                print(f"Hook {event} error: {e}")
        return results


class PluginLoader:
    """插件加载器 - 支持外部插件"""

    @staticmethod
    def load_from_directory(directory: str) -> List[Plugin]:
        """从目录加载插件"""
        plugins = []

        if not os.path.exists(directory):
            return plugins

        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(directory, filename)) as f:
                        data = json.load(f)
                        plugin = Plugin(**data)
                        plugins.append(plugin)
                except:
                    pass

        return plugins

    @staticmethod
    def load_from_module(module_path: str) -> Optional[Plugin]:
        """从模块加载插件"""
        try:
            module = importlib.import_module(module_path)
            if hasattr(module, "plugin"):
                return module.plugin
        except Exception as e:
            print(f"Failed to load plugin {module_path}: {e}")
        return None


# 全局实例
_plugin_registry = None

def get_plugin_registry() -> PluginRegistry:
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry


def install_plugin(name: str, source: str = None) -> bool:
    """安装插件"""
    registry = get_plugin_registry()

    if source:
        plugin = PluginLoader.load_from_module(source)
        if plugin:
            registry.register(plugin)
            return True
    else:
        # 从内置插件安装
        for p in registry.list_all():
            if name in p.name:
                registry.enable(p.name)
                return True

    return False


def uninstall_plugin(name: str) -> bool:
    """卸载插件"""
    registry = get_plugin_registry()
    return registry.unregister(name)


def list_plugins() -> List[Dict]:
    """列出所有插件"""
    registry = get_plugin_registry()
    return [
        {
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "enabled": p.enabled
        }
        for p in registry.list_all()
    ]