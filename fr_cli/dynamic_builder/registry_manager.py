"""
动态构建 —— 注册表管理

负责动态工具的持久化、加载和注册到 ToolRegistry。
"""
import importlib.util
import re
from typing import Any, Dict, List, Optional, Tuple

from fr_cli.conf.paths import ROOT
from fr_cli.core.result import Result
from fr_cli.core.store import JsonStore
from fr_cli.command.registry import register, get_registry


DYNAMIC_TOOLS_DIR = ROOT / "dynamic_tools"
REGISTRY_FILE = DYNAMIC_TOOLS_DIR / "registry.json"


def _ensure_dir():
    DYNAMIC_TOOLS_DIR.mkdir(parents=True, exist_ok=True)


def _registry_store() -> JsonStore:
    """返回基于当前 REGISTRY_FILE 的 JsonStore"""
    return JsonStore(REGISTRY_FILE, default=dict)


def _load_registry() -> Dict[str, Any]:
    """加载动态工具注册表元数据"""
    _ensure_dir()
    return _registry_store().read()


def _save_registry(registry: Dict[str, Any]):
    """保存动态工具注册表元数据"""
    _ensure_dir()
    _registry_store().write(registry)


def _validate_name(name: str) -> Tuple[bool, str]:
    """验证工具名是否合法"""
    if not name:
        return False, "工具名不能为空"
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return False, "工具名必须是合法的 Python 标识符"
    if name.startswith("_"):
        return False, "工具名不能以 _ 开头"
    return True, ""


def save_dynamic_tool(name: str, code: str, description: str = "", params: Optional[Dict[str, type]] = None,
                      aliases: Optional[List[str]] = None, triggers: Optional[List[str]] = None) -> Result:
    """
    保存动态工具到磁盘，返回 Result。

    Args:
        name: 工具名
        code: Python 代码
        description: 工具描述
        params: 参数字典 {param_name: type}
        aliases: 命令别名列表
        triggers: 触发关键词列表
    """
    ok, err = _validate_name(name)
    if not ok:
        return Result.fail(err)

    _ensure_dir()
    tool_path = DYNAMIC_TOOLS_DIR / f"{name}.py"
    tool_path.write_text(code, encoding="utf-8")

    registry = _load_registry()
    registry[name] = {
        "name": name,
        "description": description,
        "params": {k: t.__name__ for k, t in (params or {}).items()},
        "aliases": aliases or [],
        "triggers": triggers or [],
        "path": str(tool_path),
    }
    _save_registry(registry)
    return Result.ok(f"工具 [{name}] 已保存")


def load_dynamic_tool_code(name: str) -> Optional[str]:
    """从磁盘加载工具代码"""
    tool_path = DYNAMIC_TOOLS_DIR / f"{name}.py"
    if not tool_path.exists():
        return None
    try:
        return tool_path.read_text(encoding="utf-8")
    except Exception:
        return None


def delete_dynamic_tool(name: str) -> Result:
    """删除动态工具，返回 Result"""
    registry = _load_registry()
    if name not in registry:
        return Result.fail(f"工具 [{name}] 不存在")

    tool_path = DYNAMIC_TOOLS_DIR / f"{name}.py"
    if tool_path.exists():
        tool_path.unlink()

    registry.pop(name, None)
    _save_registry(registry)

    # 从注册表移除
    reg = get_registry()
    reg._tools.pop(name, None)
    for alias, target in list(reg._aliases.items()):
        if target == name:
            del reg._aliases[alias]

    return Result.ok(f"工具 [{name}] 已删除")


def list_dynamic_tools() -> List[Dict[str, Any]]:
    """列出所有动态工具"""
    return list(_load_registry().values())


def _type_from_name(type_name: str) -> type:
    """根据类型名字符串返回类型"""
    mapping = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
    }
    return mapping.get(type_name, str)


def _default_value_for_type(param_type: type) -> Any:
    """返回某一参数类型的安全默认值，用于动态工具自测。"""
    defaults = {
        str: "",
        int: 0,
        float: 0.0,
        bool: False,
        list: [],
        dict: {},
    }
    return defaults.get(param_type, "")


def default_kwargs_for_params(params: Optional[Dict[str, type]]) -> Dict[str, Any]:
    """根据参数类型生成默认测试参数。"""
    return {k: _default_value_for_type(v) for k, v in (params or {}).items()}


def register_dynamic_tool(name: str, code: str, meta: Optional[Dict[str, Any]] = None) -> Result:
    """
    将动态工具代码加载并注册到 ToolRegistry，返回 Result。

    Args:
        name: 工具名
        code: Python 代码
        meta: 元数据，包含 description/params/aliases/triggers
    """
    ok, err = _validate_name(name)
    if not ok:
        return Result.fail(err)

    meta = meta or {}
    description = meta.get("description", f"动态构建工具: {name}")
    params = {k: _type_from_name(v) for k, v in meta.get("params", {}).items()}
    aliases = meta.get("aliases", [])
    triggers = meta.get("triggers", [])

    # 动态加载模块
    try:
        spec = importlib.util.spec_from_loader(name, loader=None)
        module = importlib.util.module_from_spec(spec)
        exec(code, module.__dict__)
        run_fn = getattr(module, "run", None)
        if run_fn is None:
            return Result.fail("生成的代码缺少 run(deps, **kwargs) 入口函数")
    except Exception as e:
        return Result.fail(f"加载动态工具失败: {e}")

    # 包装函数，适配 ToolRegistry 的 handler 签名
    @register(
        name=name,
        description=description,
        params=params,
        aliases=aliases,
        triggers=triggers,
    )
    def _dynamic_tool_handler(deps, **kwargs):
        try:
            return run_fn(deps, **kwargs)
        except Exception as e:
            return None, f"动态工具执行失败: {e}"

    return Result.ok(f"工具 [{name}] 已注册")


def load_and_register_all_dynamic_tools() -> Tuple[int, List[str]]:
    """
    启动时从磁盘加载并注册所有动态工具。

    Returns:
        (success_count, errors)
    """
    registry = _load_registry()
    success = 0
    errors = []
    for name, meta in registry.items():
        code = load_dynamic_tool_code(name)
        if code is None:
            errors.append(f"[{name}] 代码文件丢失")
            continue
        result = register_dynamic_tool(name, code, meta)
        if result.is_ok():
            success += 1
        else:
            errors.append(f"[{name}] {result.error}")
    return success, errors
