"""
动态工具沙箱 —— 子进程侧执行器

v2.8.7 新增（P0-1 安全加固）。

由 :func:`fr_cli.dynamic_builder.sandbox.run_in_sandbox` 通过
``python -m fr_cli.dynamic_builder.sandbox_worker`` 拉起。

职责：
  1. 读 stdin 的第一行 JSON 请求（代码 + 参数 + 受限上下文）
  2. 在**受限命名空间**里执行 ``run(deps, **kwargs)``
  3. 把结果以 JSON 写回 stdout（协议见下）

协议
----
双向、逐行 JSON：

* **父 → 子**：第一行是 ``{"kind": "request", ...}``；
  之后每行是 ``{"kind": "rpc_reply", "id": N, "ok": bool, ...}``
* **子 → 父**：``{"kind": "rpc", "id": N, "obj": ..., "method": ..., ...}``
  是能力代理请求（由父进程用真实 deps 执行）；
  最后一行是 ``{"kind": "result", "ok": bool, "value": ...}``

子进程侧的三重限制
------------------
* **受限 builtins** —— ``open`` / ``eval`` / ``exec`` / ``compile`` / ``input``
  等被从 builtins 里剔除，用户代码引用即 ``NameError``
* **受限 import** —— ``__import__`` 被换成守卫，命中黑名单直接 ``ImportError``；
  放行的模块还会被清洗掉夹带的黑名单属性（如 ``pathlib.os``）
* **受限资源** —— CPU / 内存 / 文件大小 / 进程数由 rlimit 兜底

用户代码的 stdout 被重定向到 stderr —— 保证 stdout 只有协议数据。
"""
from __future__ import annotations

import builtins
import json
import sys
import threading
import traceback
import types
from typing import Any, Dict, Optional

# 协议用的真实 stdout（用户代码的 stdout 会被重定向到 stderr）
_PROTOCOL_OUT = sys.stdout

from fr_cli.dynamic_builder.sandbox import (  # noqa: E402
    BLOCKED_BUILTINS,
    BLOCKED_MODULES,
    apply_child_limits,
    from_wire,
    to_wire,
)


# ------------------------------------------------------------------
# 受限 builtins / import 守卫
# ------------------------------------------------------------------

def _sanitize_module(mod: Any) -> None:
    """把被放行模块里夹带的黑名单模块属性剔除。

    例：``import pathlib`` 会让 ``pathlib.os`` 可见，从而绕过 ``open()``
    禁令 —— 这里把 ``pathlib.__dict__["os"]`` 删掉。
    """
    try:
        names = list(vars(mod).keys())
    except Exception:
        return
    for attr in names:
        try:
            value = getattr(mod, attr)
        except Exception:
            continue
        mod_name = getattr(value, "__name__", None)
        if isinstance(mod_name, str) and mod_name.split(".")[0] in BLOCKED_MODULES:
            try:
                delattr(mod, attr)
            except Exception:
                pass


def _restricted_builtins() -> Dict[str, Any]:
    """构造受限 builtins 字典。"""
    allowed = dict(vars(builtins))
    real_import = allowed["__import__"]
    for name in BLOCKED_BUILTINS:
        allowed.pop(name, None)

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root in BLOCKED_MODULES:
            raise ImportError(
                f"沙箱禁止导入 '{name}'"
                "（文件操作请用 deps.vfs，网络访问请用 deps.web_c）"
            )
        mod = real_import(name, globals, locals, fromlist, level)
        _sanitize_module(mod)
        return mod

    allowed["__import__"] = guarded_import
    return allowed


# ------------------------------------------------------------------
# RPC 客户端（子进程侧）
# ------------------------------------------------------------------

class _RpcClient:
    """把能力调用转回父进程执行。"""

    def __init__(self, stdin, stdout) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._seq = 0
        self._lock = threading.Lock()

    def call(self, obj_name: str, method_name: str, args, kwargs):
        with self._lock:
            self._seq += 1
            rid = self._seq
            request = {
                "kind": "rpc",
                "id": rid,
                "obj": obj_name,
                "method": method_name,
                "args": [to_wire(a) for a in args],
                "kwargs": {k: to_wire(v) for k, v in (kwargs or {}).items()},
            }
            self._write(request)
            reply = self._read()
        if not isinstance(reply, dict):
            raise RuntimeError("沙箱 RPC 通道已关闭")
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error") or "RPC 调用失败")
        return from_wire(reply.get("value"))

    # ---------- 底层读写 ----------

    def _write(self, payload: Dict[str, Any]) -> None:
        self._stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._stdout.flush()

    def _read(self) -> Optional[Dict[str, Any]]:
        line = self._stdin.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except Exception:
            return None


class _RpcProxy:
    """能力代理 —— 任何属性访问都变成一次回父进程的 RPC 调用。"""

    def __init__(self, rpc: _RpcClient, obj_name: str) -> None:
        object.__setattr__(self, "_rpc", rpc)
        object.__setattr__(self, "_obj_name", obj_name)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _call(*args, **kwargs):
            return self._rpc.call(self._obj_name, name, args, kwargs)

        _call.__name__ = name
        return _call


class _DenySecurity:
    """子进程里的 security 桩 —— 一律拒绝。

    授权永远在父进程做（REPL 终端 / bot 聊天窗口），子进程无权放行任何操作。
    """

    name = "deny-all"

    def check(self, *args, **kwargs) -> bool:
        return False

    def permission_decision(self, *args, **kwargs) -> str:
        return "deny"

    def check_tool_permission(self, *args, **kwargs) -> bool:
        return False

    def unconfirm_all(self) -> None:
        return None


# ------------------------------------------------------------------
# 受限 deps 装配
# ------------------------------------------------------------------

def _build_deps(request: Dict[str, Any], rpc: _RpcClient):
    """构造子进程侧的 deps 命名空间。"""
    from fr_cli.weapon.fs import VFS

    allowed_dirs = request.get("allowed_dirs") or []
    vfs = VFS(allowed_dirs) if allowed_dirs else VFS([])
    vfs_cwd = request.get("vfs_cwd")
    if vfs_cwd:
        vfs.cwd = vfs_cwd

    return types.SimpleNamespace(
        vfs=vfs,
        mail_c=_RpcProxy(rpc, "mail_c"),
        web_c=_RpcProxy(rpc, "web_c"),
        disk_c=_RpcProxy(rpc, "disk_c"),
        plugins=dict(request.get("plugins") or {}),
        lang=request.get("lang") or "zh",
        security=_DenySecurity(),
        cfg=dict(request.get("cfg") or {}),
        client=_RpcProxy(rpc, "client"),
        model_name=request.get("model_name") or "",
        provider=request.get("provider") or "",
        mcp=_RpcProxy(rpc, "mcp"),
    )


# ------------------------------------------------------------------
# 用户代码执行
# ------------------------------------------------------------------

def _load_module(code: str):
    """把用户代码加载成模块（受限 builtins）。"""
    module = types.ModuleType("dynamic_tool")
    module.__dict__["__builtins__"] = _restricted_builtins()
    module.__dict__["__name__"] = "dynamic_tool"
    module.__dict__["__file__"] = "<dynamic_tool>"
    exec(compile(code, "<dynamic_tool>", "exec"), module.__dict__)
    return module


def _filter_kwargs(run_fn, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """按 run 的签名裁剪 kwargs。

    标准契约是 ``run(deps, **kwargs)``；但历史动态工具可能写成
    ``run(deps, name='')`` 这种没有 ``**kwargs`` 的形式 —— 此时只传
    它真正接受的参数，避免 TypeError。
    """
    try:
        import inspect
        params = inspect.signature(run_fn).parameters
    except Exception:
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    allowed = {
        name for name, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {k: v for k, v in kwargs.items() if k in allowed}


def _execute(request: Dict[str, Any], rpc: _RpcClient):
    """执行用户代码的 run(deps, **kwargs)。"""
    code = request.get("code") or ""
    kwargs = request.get("kwargs") or {}

    module = _load_module(code)
    run_fn = module.__dict__.get("run")
    if run_fn is None or not callable(run_fn):
        raise RuntimeError("生成的代码缺少 run(deps, **kwargs) 入口函数")

    deps = _build_deps(request, rpc)
    return run_fn(deps, **_filter_kwargs(run_fn, kwargs))


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def _emit(payload: Dict[str, Any]) -> None:
    """把协议消息写到真实 stdout。"""
    _PROTOCOL_OUT.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _PROTOCOL_OUT.flush()


def main() -> int:
    """子进程主流程。"""
    raw = sys.stdin.readline()
    try:
        request = json.loads(raw) if raw else {}
    except Exception as e:
        _emit({"kind": "result", "ok": False, "error": f"沙箱请求解析失败: {e}"})
        return 1

    # 资源限额（父进程传下来的）
    apply_child_limits(request.get("limits") or {})

    # 用户代码的 stdout 全部转到 stderr —— 保证 stdout 只有协议数据
    sys.stdout = sys.stderr

    rpc = _RpcClient(sys.stdin, _PROTOCOL_OUT)
    try:
        value = _execute(request, rpc)
    except BaseException as e:  # noqa: BLE001 —— 含 SystemExit / KeyboardInterrupt
        _emit({
            "kind": "result",
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()[-4000:],
        })
        return 1

    try:
        _emit({"kind": "result", "ok": True, "value": to_wire(value)})
    except Exception as e:
        _emit({"kind": "result", "ok": False, "error": f"结果序列化失败: {e}"})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
