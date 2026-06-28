"""
v3 Container —— 简易依赖注入容器

v2.x:AppState 是上帝对象,所有子系统都直接挂在它上面。
v3:Container 是"注册表 + 工厂",按 key 存取,支持 singleton/transient scope,
可注入依赖。

特性:
- 单例(默认)/ transient 两种 scope
- 工厂函数(支持延迟初始化)
- 测试 override(register 覆盖)
- type hint 自动注入(简化版)
"""
from __future__ import annotations

import inspect
import logging
import threading
from typing import Any, Callable, Dict, Optional, Type

log = logging.getLogger(__name__)

# sentinel:区别于 None(可作为合法值)
_MISSING = object()


class Registration:
    """注册项

    Attributes:
        factory: 工厂函数(可返回实例)
        instance: 单例实例(singleton 时缓存)
        scope: "singleton" / "transient"
        name: 可选名称(同类型多实例)
    """
    __slots__ = ("key", "factory", "instance", "scope", "name", "_lock")

    def __init__(self, key: str, factory: Callable,
                 scope: str = "singleton", name: Optional[str] = None):
        self.key = key
        self.factory = factory
        self.instance = None
        self.scope = scope
        self.name = name
        self._lock = threading.Lock()


class Container:
    """依赖注入容器"""

    def __init__(self, parent: Optional["Container"] = None):
        self._registry: Dict[str, Registration] = {}
        self._lock = threading.RLock()
        self._parent = parent  # 支持父子容器

    def register(self, key: str,
                 factory: Optional[Callable] = None,
                 instance: Any = None,
                 scope: str = "singleton",
                 name: Optional[str] = None,
                 override: bool = True) -> Registration:
        """注册一个依赖

        Args:
            key: 依赖 key(如 "config", "vfs")
            factory: 工厂函数 fn() -> instance
            instance: 直接提供实例(替代 factory)
            scope: "singleton"(缓存)或 "transient"(每次新建)
            name: 同类型多实例时的名字
            override: True 时覆盖已有注册
        """
        with self._lock:
            full_key = self._make_key(key, name)
            if full_key in self._registry and not override:
                log.debug(f"register: {full_key} already exists, skip")
                return self._registry[full_key]

            if instance is not None:
                reg = Registration(full_key, lambda: instance, scope="singleton")
                reg.instance = instance
            else:
                if factory is None:
                    factory = self._default_factory(key)
                reg = Registration(full_key, factory, scope=scope, name=name)

            self._registry[full_key] = reg
            log.debug(f"register: {full_key} scope={scope}")
            return reg

    def register_class(self, cls: Type, scope: str = "singleton",
                       name: Optional[str] = None) -> Registration:
        """注册一个类(用类本身当 factory)"""
        return self.register(self._key_from_class(cls), cls, scope=scope, name=name)

    def register_instance(self, instance: Any,
                          name: Optional[str] = None) -> Registration:
        """注册一个已存在实例"""
        key = self._key_from_instance(instance)
        return self.register(key, instance=instance, scope="singleton", name=name)

    def get(self, key: str, default: Any = ..., name: Optional[str] = None) -> Any:
        """获取一个依赖

        Args:
            key: key 或 type(用 _key_from_class 自动转换)
            default: 找不到时返回的默认值,默认 sentinel 表示抛错
            name: 同类型多实例的名字
        """
        if isinstance(key, type):
            key = self._key_from_class(key)

        full_key = self._make_key(key, name)
        with self._lock:
            reg = self._registry.get(full_key)
            # 找不到时查父容器
            if reg is None and self._parent is not None:
                if default is not ...:
                    return self._parent.get(key, default=default, name=name)
                return self._parent.get(key, name=name)

        if reg is None:
            if default is not ...:
                return default
            raise KeyError(f"dependency not registered: {full_key}")

        if reg.scope == "singleton":
            if reg.instance is None:
                with reg._lock:
                    if reg.instance is None:
                        reg.instance = reg.factory()
            return reg.instance
        return reg.factory()

    def has(self, key: str, name: Optional[str] = None) -> bool:
        """检查依赖是否注册"""
        if isinstance(key, type):
            key = self._key_from_class(key)
        full_key = self._make_key(key, name)
        with self._lock:
            return full_key in self._registry

    def remove(self, key: str, name: Optional[str] = None) -> bool:
        """移除一个注册"""
        if isinstance(key, type):
            key = self._key_from_class(key)
        full_key = self._make_key(key, name)
        with self._lock:
            return self._registry.pop(full_key, None) is not None

    def clear(self):
        """清空(测试用)"""
        with self._lock:
            self._registry.clear()

    def keys(self):
        """所有 key 列表"""
        with self._lock:
            return list(self._registry.keys())

    # ---------------- 工具方法 ----------------

    def inject(self, func: Callable) -> Callable:
        """装饰器:自动注入 func 的参数

        解析规则:
          - 显式传入的参数不覆盖
          - 有 type hint 的 → 优先按类型解析,fallback 按名字
          - 有默认值且容器里也没有 → 用默认值
          - 都拿不到 → 报错(TypeError)

        用法:
            @container.inject
            def my_func(vfs: VFS, config: Config, extra="default"):
                ...
        """
        sig = inspect.signature(func)

        def wrapper(*args, **kwargs):
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()  # 让默认值参与,但会被覆盖

            for pname, param in sig.parameters.items():
                # 显式传入的参数:不覆盖
                if pname in bound.arguments and pname in kwargs:
                    continue
                if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                                 inspect.Parameter.VAR_KEYWORD):
                    continue

                # 优先按 type 解析
                value = _MISSING
                if param.annotation is not inspect.Parameter.empty:
                    try:
                        value = self.get(param.annotation)
                    except (KeyError, TypeError):
                        pass
                # fallback: 按名字
                if value is _MISSING:
                    try:
                        value = self.get(pname)
                    except KeyError:
                        pass

                if value is not _MISSING:
                    bound.arguments[pname] = value
                elif param.default is inspect.Parameter.empty:
                    # 必须提供
                    raise TypeError(
                        f"inject: cannot resolve parameter '{pname}' "
                        f"for {func.__name__}; not in container and no default"
                    )
                # 否则用默认值(bind_partial + apply_defaults 已经填过)

            return func(*bound.args, **bound.kwargs)

        wrapper.__wrapped__ = func
        wrapper.__signature__ = sig
        return wrapper

    def _make_key(self, key: str, name: Optional[str]) -> str:
        if name:
            return f"{key}::{name}"
        return key

    def _key_from_class(self, cls: Type) -> str:
        return f"class:{cls.__module__}.{cls.__name__}"

    def _key_from_instance(self, instance: Any) -> str:
        return f"class:{type(instance).__module__}.{type(instance).__name__}"

    def _default_factory(self, key: str) -> Callable:
        """缺省 factory(用于 register without factory)"""
        def factory():
            raise NotImplementedError(f"no factory for {key}")
        return factory

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __repr__(self):
        return f"Container(keys={list(self.keys())})"




# ---------------- 全局容器 ----------------

_global_container: Optional[Container] = None
_global_lock = threading.Lock()


def global_container() -> Container:
    """全局容器(单例)"""
    global _global_container
    with _global_lock:
        if _global_container is None:
            _global_container = Container()
        return _global_container


def reset_global_container():
    """重置全局容器(测试用)"""
    global _global_container
    with _global_lock:
        _global_container = None
