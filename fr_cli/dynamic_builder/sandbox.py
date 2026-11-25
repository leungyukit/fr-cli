"""
动态工具沙箱 —— 父进程侧执行器（子进程隔离）

v2.8.7 新增（P0-1 安全加固）。

问题
----
``/build`` 动态构建出来的工具，是 **LLM 生成的代码**，却直接在
fr-cli **主进程**里 ``exec()``：

    fr_cli/dynamic_builder/registry_manager.py
        exec(code, module.__dict__)      # ← LLM 生成代码在主进程裸跑

后果：
  - 无沙箱、无超时、无资源限制 —— 死循环 / 内存爆炸 / 崩溃会拖垮整个 fr-cli
  - 每次 fr-cli 启动都会 exec 一遍 ``~/.fr_cli/dynamic_tools/*.py``
  - bot 场景下这是**完整的 RCE 链**：平台消息 → prompt injection → 模型调
    ``/build`` → 任意代码在主进程执行

设计
----
**父进程授权，子进程执行。**

  ┌─ 父进程（fr-cli）────────────────────┐        ┌─ 子进程（受限）──────────┐
  │ 静态 AST 校验                        │  stdin │ 受限 builtins            │
  │   ↓ 通过                            │ ─────→ │ 受限 import 守卫          │
  │ 安全确认（sec_exec，走 Y/A/F/N）      │        │ rlimit 资源限额           │
  │   ↓ 放行                            │        │  ├ vfs   真实 VFS（路径沙盒）│
  │ 派生子进程 + 最小环境变量            │ stdout │  ├ cfg   脱敏副本          │
  │   ↓                                 │ ←───── │  ├ security 拒绝一切       │
  │ 宿主线程：收子进程 RPC 请求 ─────────┼──rpc───┤  └ web_c/mail_c/…  ←代理──┐ │
  │   ↓ 用**真实** deps 执行，            │        │      执行 run(deps, **kw) │ │
  │     按 sec_* 走安全检查              │        │ 结果 JSON 回传 stdout      │
  └─────────────────────────────────────┘        └───────────────────────────┘

关键取舍
--------
* **凭证不出主进程**：``cfg`` 传给子进程的是**脱敏副本**（api key / secret /
  token / password 全部剔除）。
* **网络不出沙箱**：``requests`` / ``urllib`` / ``socket`` 等模块被静态校验
  拦截；网络访问必须走 ``deps.web_c``，由父进程执行并走 ``sec_fetch_web``。
* **文件只走 VFS**：``open()`` 内置函数被静态校验 + 运行时 builtins 裁剪双重
  拦截；文件操作必须走 ``deps.vfs``（VFS 自带路径沙盒，防 ``../`` 逃逸）。
* **授权永远在父进程**：子进程里的 ``deps.security`` 是一律拒绝的桩 ——
  因为确认交互只能在父进程做（REPL 终端 / bot 聊天窗口）。
* **RPC 调用同样受管控**：子进程请求 ``web_c.search`` 时，父进程会先用真实
  ``SecurityManager`` 走一遍 ``sec_fetch_web`` 确认，再执行。
* **协议走 stdin/stdout 双向管道**（而非 socketpair）—— Windows 上
  ``pass_fds`` 不可用，管道方案跨平台一致。

已知边界（诚实声明）
--------------------
子进程**不是**操作系统级沙箱：它仍能用自己的 Python 能力访问真实文件系统
（只要不写 ``open()``）与网络（只要不写 socket），第三方 pip 依赖也能读写
本机文件。本模块提供的是
**崩溃隔离 + 超时 + 资源限额 + 凭证隔离 + 静态白名单 + 运行时 import 守卫**。
要真正的内核级隔离需要 Landlock（Linux）/ Seatbelt（macOS），属独立议题。
"""
from __future__ import annotations

import ast
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from typing import Any, Dict, List, Optional

from fr_cli.core.result import Result

__all__ = [
    "validate_dynamic_code",
    "run_in_sandbox",
    "SandboxError",
    "DEFAULT_TIMEOUT",
    "BLOCKED_MODULES",
    "BLOCKED_BUILTINS",
    "DEFAULT_LIMITS",
    "apply_child_limits",
    "to_wire",
    "from_wire",
]


# ------------------------------------------------------------------
# 静态校验白名单
# ------------------------------------------------------------------

#: 禁止导入的模块 —— 进程控制 / 原始系统调用 / 动态加载 / 反序列化
BLOCKED_MODULES = frozenset({
    # 进程与系统
    "os", "sys", "subprocess", "shutil", "pty", "fcntl", "signal",
    "resource", "multiprocessing", "threading", "_thread", "gc", "atexit",
    # 动态加载与代码执行
    "importlib", "imp", "runpy", "code", "codeop", "exec", "builtins",
    "pickle", "cPickle", "marshal", "shelve", "ctypes", "inspect",
    "pdb", "bdb", "trace", "tracemalloc", "site", "sysconfig",
    "distutils", "setuptools", "pip",
    # 原始网络
    "socket", "ssl", "select", "selectors", "asyncio", "urllib",
    "urllib2", "urllib3", "http", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "imaplib", "poplib", "telnetlib", "xmlrpc",
    "webbrowser", "ssl",
    # 文件系统便利模块（会顺带带出 os 模块，绕过 open() 禁令）
    "pathlib", "glob", "fnmatch", "fileinput", "tempfile",
    # fr-cli 自身（防止动态代码绕过沙箱调用内部能力 / 读取凭证文件）
    "fr_cli",
})

#: 禁止调用的内置函数
BLOCKED_BUILTINS = frozenset({
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "memoryview", "help", "exit", "quit",
})

#: 禁止访问的 dunder 属性（逃逸手段）
BLOCKED_DUNDER = frozenset({
    "__class__", "__globals__", "__subclasses__", "__builtins__", "__code__",
    "__closure__", "__mro__", "__bases__", "__base__", "__reduce__",
    "__reduce_ex__", "__getattribute__", "__dict__", "__loader__",
    "__spec__", "__init_subclass__", "__subclasshook__", "__get__",
    "__set_name__", "__new__", "__delattr__", "__setattr__", "__delete__",
    "__func__", "__self__", "__objclass__", "__wrapped__", "__module__",
})

#: 允许读取的 dunder —— 协议方法与元信息，不是逃逸手段
SAFE_DUNDERS = frozenset({
    "__name__", "__doc__", "__version__", "__file__", "__all__",
    "__init__", "__iter__", "__next__", "__len__", "__getitem__",
    "__enter__", "__exit__", "__call__", "__str__", "__repr__",
    "__eq__", "__hash__", "__contains__", "__bool__", "__format__",
})

#: 默认执行超时（秒）
DEFAULT_TIMEOUT = 30

#: 子进程资源限额默认值
DEFAULT_LIMITS: Dict[str, int] = {
    "cpu_seconds": DEFAULT_TIMEOUT,
    "mem_bytes": 2 * 1024 * 1024 * 1024,      # 2 GiB
    "fsize_bytes": 64 * 1024 * 1024,         # 64 MiB
    "nproc": 64,
}

#: RPC 服务名 → 安全类别（父进程执行前走一遍真实确认）
_RPC_SERVICE_SECURITY = {
    "web_c": "sec_fetch_web",
    "mail_c": "sec_read_mail",
    "disk_c": "sec_write",
    "client": "sec_exec",
    "mcp": "sec_mcp_call",
}


class SandboxError(Exception):
    """沙箱执行异常。"""


# ------------------------------------------------------------------
# 静态校验
# ------------------------------------------------------------------

def _is_blocked_dunder(attr: str) -> bool:
    if attr in SAFE_DUNDERS:
        return False
    if attr in BLOCKED_DUNDER:
        return True
    # 其它双下划线属性一律拦截（逃逸手段大多长这样）
    return attr.startswith("__") and attr.endswith("__")


def validate_dynamic_code(code: str) -> Result:
    """静态校验动态工具代码。

    检查项：
      1. 语法正确
      2. 存在 ``run(deps, **kwargs)`` 入口
      3. 没有导入被禁模块（进程 / 原始网络 / 动态加载 / 反序列化）
      4. 没有调用被禁内置函数（``open`` / ``eval`` / ``exec`` ...）
      5. 没有访问危险 dunder 属性（``__class__`` / ``__globals__`` ...）

    注意：这是**纵深防御的一层**，不是唯一防线 —— 子进程隔离、超时、
    资源限额、凭证脱敏、运行时 import 守卫共同构成完整防护。

    Returns:
        ``Result.ok(...)`` 表示通过；``Result.fail(...)`` 携带拒绝原因。
    """
    if not code or not code.strip():
        return Result.fail("代码为空")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return Result.fail(f"代码语法错误: 第 {e.lineno} 行 {e.msg}")

    # 1) run(deps, **kwargs) 入口
    run_fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            run_fn = node
            break
    if run_fn is None:
        return Result.fail("生成的代码缺少 run(deps, **kwargs) 入口函数")
    args = run_fn.args
    # 必须能接收 deps（至少一个位置参数）
    has_deps = bool(args.posonlyargs) or bool(args.args)
    if not has_deps:
        return Result.fail("run 入口签名必须是 run(deps, **kwargs)（至少需要一个位置参数接收 deps）")

    # 2~5) 危险构造
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    return Result.fail(
                        f"禁止导入模块 '{alias.name}'（沙箱内不可用；"
                        f"网络请用 deps.web_c，文件请用 deps.vfs）"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                return Result.fail(
                    f"禁止导入模块 '{node.module}'（沙箱内不可用；"
                    f"网络请用 deps.web_c，文件请用 deps.vfs）"
                )
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in BLOCKED_BUILTINS:
                hint = "（文件操作请用 deps.vfs）" if fn.id == "open" else ""
                return Result.fail(f"禁止调用内置函数 '{fn.id}'{hint}")
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_BUILTINS:
                hint = "（文件操作请用 deps.vfs）" if node.id == "open" else ""
                return Result.fail(f"禁止引用内置函数 '{node.id}'{hint}")
        elif isinstance(node, ast.Attribute):
            if _is_blocked_dunder(node.attr):
                return Result.fail(f"禁止访问属性 '{node.attr}'")

    return Result.ok("静态校验通过")


# ------------------------------------------------------------------
# 线上协议编解码（父 / 子进程共用）
# ------------------------------------------------------------------

#: 迭代器物化上限（防止无限生成器打爆内存）
_ITER_LIMIT = 5000


def to_wire(obj: Any) -> Dict[str, Any]:
    """把任意对象编码成可 JSON 序列化的信封。"""
    if obj is None:
        return {"t": "none"}
    if isinstance(obj, bool):
        return {"t": "bool", "v": obj}
    if isinstance(obj, int):
        return {"t": "int", "v": obj}
    if isinstance(obj, float):
        return {"t": "float", "v": obj}
    if isinstance(obj, str):
        return {"t": "str", "v": obj}
    if isinstance(obj, (bytes, bytearray)):
        return {"t": "repr", "v": repr(bytes(obj))}
    if isinstance(obj, list):
        return {"t": "list", "v": [to_wire(x) for x in obj]}
    if isinstance(obj, tuple):
        return {"t": "tuple", "v": [to_wire(x) for x in obj]}
    if isinstance(obj, set):
        return {"t": "list", "v": [to_wire(x) for x in obj]}
    if isinstance(obj, dict):
        return {"t": "dict", "v": {str(k): to_wire(v) for k, v in obj.items()}}
    if isinstance(obj, Result):
        return {
            "t": "result",
            "v": {"ok": bool(obj.is_ok()), "data": to_wire(obj.data), "error": obj.error},
        }
    # 生成器 / 迭代器（如 LLM 的 stream_chat）—— 物化成列表再编码
    if hasattr(obj, "__next__") and hasattr(obj, "__iter__"):
        items: List[Any] = []
        try:
            for item in obj:
                items.append(to_wire(item))
                if len(items) >= _ITER_LIMIT:
                    break
        except Exception:
            pass
        return {"t": "list", "v": items}
    return {"t": "repr", "v": repr(obj)}


def from_wire(env: Any) -> Any:
    """解码 :func:`to_wire` 的信封。无法还原时退化为 repr 字符串。"""
    if not isinstance(env, dict) or "t" not in env:
        return env
    kind = env.get("t")
    val = env.get("v")
    if kind == "none":
        return None
    if kind in ("bool", "int", "float", "str"):
        return val
    if kind == "list":
        return [from_wire(x) for x in (val or [])]
    if kind == "tuple":
        return tuple(from_wire(x) for x in (val or []))
    if kind == "dict":
        return {k: from_wire(v) for k, v in (val or {}).items()}
    if kind == "result":
        data = from_wire((val or {}).get("data"))
        error = (val or {}).get("error")
        return Result.ok(data) if error is None else Result.fail(error)
    if kind == "repr":
        return val
    return val


# ------------------------------------------------------------------
# 配置脱敏
# ------------------------------------------------------------------

_SENSITIVE_NAMES = frozenset({
    "key", "api_key", "apikey", "secret", "token", "access_token",
    "refresh_token", "password", "passwd", "credential", "credentials",
    "auth", "authorization", "session_key", "private_key",
})
_SENSITIVE_RE = re.compile(r"(secret|token|password|passwd|credential|api_?key)", re.I)


def _scrub(obj: Any, depth: int = 0) -> Any:
    """递归剔除配置里的凭证。"""
    if depth > 12:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            if key.lower() in _SENSITIVE_NAMES or _SENSITIVE_RE.search(key):
                out[key] = "***"
            else:
                out[key] = _scrub(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_scrub(x, depth + 1) for x in obj]
    return obj


# ------------------------------------------------------------------
# 资源限额
# ------------------------------------------------------------------

def apply_child_limits(limits: Optional[Dict[str, int]] = None) -> None:
    """在**子进程内**设置资源限额（POSIX）。

    放在子进程侧而不是 ``preexec_fn``，是因为 fr-cli 主进程是多线程的
    （cron / RAG watcher / MCP 发现），``preexec_fn`` 在多线程进程里 fork
    存在死锁风险。

    Args:
        limits: 限额覆盖项（cpu_seconds / mem_bytes / fsize_bytes / nproc）
    """
    merged = dict(DEFAULT_LIMITS)
    merged.update(limits or {})
    try:
        import resource
    except ImportError:
        return  # Windows / 无 resource 模块 —— 限额不可用，其余防护仍在

    pairs = (
        ("RLIMIT_CPU", int(merged["cpu_seconds"])),
        ("RLIMIT_FSIZE", int(merged["fsize_bytes"])),
        ("RLIMIT_NPROC", int(merged["nproc"])),
        ("RLIMIT_AS", int(merged["mem_bytes"])),
    )
    for name, value in pairs:
        attr = getattr(resource, name, None)
        if attr is None:
            continue
        try:
            # 软硬限额同时收紧；只许收紧、不许放宽（rlimit 不可逆）
            cur_soft, cur_hard = resource.getrlimit(attr)
            soft = value
            if cur_soft != resource.RLIM_INFINITY:
                soft = min(soft, cur_soft)
            if cur_hard != resource.RLIM_INFINITY:
                soft = min(soft, cur_hard)
            resource.setrlimit(attr, (soft, cur_hard))
        except Exception:
            # 某些平台 / 某些限额不被支持 —— 逐项容错
            continue


# ------------------------------------------------------------------
# 子进程宿主（父进程侧）
# ------------------------------------------------------------------

def _security_key_for(obj_name: str, method_name: str) -> Optional[str]:
    """服务 + 方法 → 安全类别。"""
    if obj_name == "mail_c":
        return "sec_send_mail" if "send" in method_name.lower() else "sec_read_mail"
    return _RPC_SERVICE_SECURITY.get(obj_name)


class _SandboxHost:
    """父进程侧的沙箱宿主。

    职责：
      - 读子进程 stdout：``rpc`` 消息 → 用**真实** deps 执行并回写 stdin；
        ``result`` 消息 → 记录最终结果
      - 执行 RPC 前按 ``sec_*`` 走一遍真实安全确认
    """

    def __init__(self, proc, deps):
        self._proc = proc
        self._deps = deps
        self.result: Optional[Dict[str, Any]] = None
        self.result_ready = threading.Event()
        self._stdin_lock = threading.Lock()

    # ---------- 读循环 ----------

    def read_loop(self) -> None:
        stream = self._proc.stdout
        try:
            for raw in stream:
                line = raw.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                kind = msg.get("kind")
                if kind == "rpc":
                    self._handle_rpc(msg)
                elif kind == "result":
                    self.result = msg
                    self.result_ready.set()
        except Exception:
            pass
        finally:
            self.result_ready.set()

    # ---------- RPC 处理 ----------

    def _handle_rpc(self, msg: Dict[str, Any]) -> None:
        rid = msg.get("id")
        obj_name = msg.get("obj") or ""
        method_name = msg.get("method") or ""
        args = [from_wire(a) for a in (msg.get("args") or [])]
        kwargs = {k: from_wire(v) for k, v in (msg.get("kwargs") or {}).items()}

        try:
            target = getattr(self._deps, obj_name, None)
            if target is None:
                self._reply(rid, False, error=f"能力 '{obj_name}' 不可用")
                return
            method = getattr(target, method_name, None)
            if method is None or not callable(method):
                self._reply(rid, False, error=f"能力 '{obj_name}' 没有方法 '{method_name}'")
                return

            # 授权：走父进程的真实 SecurityManager（REPL 终端确认 / bot 聊天确认）
            sec_key = _security_key_for(obj_name, method_name)
            security = getattr(self._deps, "security", None)
            if sec_key and security is not None:
                if not security.check(sec_key, f"{obj_name}.{method_name}"):
                    self._reply(rid, False, error="用户拒绝了该操作")
                    return

            value = method(*args, **kwargs)
            self._reply(rid, True, value=to_wire(value))
        except Exception as e:
            self._reply(rid, False, error=f"{type(e).__name__}: {e}")

    def _reply(self, rid: Any, ok: bool, value: Any = None, error: str = "") -> None:
        payload = {"kind": "rpc_reply", "id": rid, "ok": bool(ok)}
        if ok:
            payload["value"] = value
        else:
            payload["error"] = error
        self._write(payload)

    def _write(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._stdin_lock:
            stdin = self._proc.stdin
            if stdin is None:
                return
            try:
                stdin.write(line)
                stdin.flush()
            except Exception:
                pass  # 子进程已退出 —— 忽略


# ------------------------------------------------------------------
# 子进程启动
# ------------------------------------------------------------------

def _child_env(home: str) -> Dict[str, str]:
    """最小化环境变量 —— 只保留运行 Python 必需的。"""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "HOME": home,
        "TMPDIR": home,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_COLOR": "1",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }
    # 让子进程能 import fr_cli（editable 安装 / 源码目录两种情况都覆盖）
    paths: List[str] = []
    for p in sys.path:
        candidate = p or os.getcwd()
        if candidate and os.path.isdir(candidate) and candidate not in paths:
            paths.append(candidate)
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def _build_request(code: str, kwargs: Dict[str, Any], deps, timeout: int) -> Dict[str, Any]:
    """组装传给子进程的请求。"""
    vfs = getattr(deps, "vfs", None)
    allowed_dirs = list(getattr(vfs, "ds", []) or []) if vfs is not None else []
    cfg = _scrub(getattr(deps, "cfg", {}) or {})
    plugins = dict(getattr(deps, "plugins", {}) or {})
    limits = dict(DEFAULT_LIMITS)
    limits["cpu_seconds"] = max(1, int(timeout))
    return {
        "kind": "request",
        "code": code,
        "kwargs": kwargs or {},
        "allowed_dirs": allowed_dirs,
        "vfs_cwd": getattr(vfs, "cwd", None),
        "cfg": cfg,
        "lang": getattr(deps, "lang", "zh"),
        "model_name": getattr(deps, "model_name", ""),
        "provider": getattr(deps, "provider", "") or "",
        "plugins": plugins,
        "limits": limits,
    }


def run_in_sandbox(name: str, code: str, kwargs: Dict[str, Any], deps,
                   timeout: int = DEFAULT_TIMEOUT) -> Result:
    """在子进程沙箱里执行动态工具。

    Args:
        name:    工具名（用于日志与错误信息）
        code:    工具代码（``run(deps, **kwargs)``）
        kwargs:  工具参数
        deps:    父进程的依赖命名空间（``SimpleNamespace``）
        timeout: 超时秒数

    Returns:
        ``Result`` —— 成功时 data 是工具返回值；失败时 error 是原因。
    """
    # 1) 静态校验（注册时已做过一次，这里再做一次做纵深防御）
    check = validate_dynamic_code(code)
    if check.is_fail():
        return Result.fail(f"沙箱拒绝执行 [{name}]: {check.error}")

    request = _build_request(code, kwargs, deps, timeout)

    home = tempfile.mkdtemp(prefix="fr_cli_sandbox_")
    env = _child_env(home)
    stderr_path = os.path.join(home, "stderr.log")
    proc = None
    host = None
    try:
        with open(stderr_path, "wb") as err_file:
            proc = subprocess.Popen(
                [sys.executable, "-m", "fr_cli.dynamic_builder.sandbox_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=err_file,          # 落文件 —— 避免 stderr 管道写满导致子进程阻塞
                env=env,
                cwd=home,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                # 子进程独立成组 —— 超时时能连它自己 fork 的子孙一起杀掉
                # （_kill_process 会先核对 pgid，绝不会误杀父进程所在组）
                start_new_session=(os.name == "posix"),
            )
            host = _SandboxHost(proc, deps)

            # 先发请求，再起读线程 —— 避免 RPC 回复与请求写乱序
            payload = json.dumps(request, ensure_ascii=False, default=str)
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except Exception as e:
                _kill_process(proc)
                return Result.fail(f"动态工具 [{name}] 沙箱通信失败: {e}")

            reader = threading.Thread(
                target=host.read_loop, daemon=True, name="fr-cli-sandbox-reader"
            )
            reader.start()

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_process(proc)
                return Result.fail(f"动态工具 [{name}] 执行超时（{timeout}s），已终止")

            # 子进程已退出 —— 等读线程把最后一条 result 收完
            host.result_ready.wait(timeout=5)
            reader.join(timeout=2)

        response = host.result if host else None
        stderr_tail = _read_tail(stderr_path)
    except Exception as e:
        if proc is not None:
            _kill_process(proc)
        return Result.fail(f"动态工具 [{name}] 沙箱启动失败: {e}")
    finally:
        if proc is not None:
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
        _cleanup_home(home)

    if response is None:
        detail = stderr_tail
        return Result.fail(
            f"动态工具 [{name}] 未返回有效结果"
            + (f"\n{detail}" if detail else "")
        )

    if response.get("ok"):
        value = from_wire(response.get("value"))
        if isinstance(value, Result):
            return value
        # 动态工具的契约是返回 (result, error) —— 保留原有语义
        if isinstance(value, tuple) and len(value) == 2:
            return Result.from_tuple(value[0], value[1])
        return Result.ok(value)

    error = response.get("error") or "未知错误"
    trace = response.get("traceback") or ""
    return Result.fail(
        f"动态工具 [{name}] 执行失败: {error}"
        + (f"\n{trace}" if trace else "")
        + (f"\n{stderr_tail}" if stderr_tail and not trace else "")
    )


def _kill_process(proc) -> None:
    """超时/异常时杀掉整个进程组（子进程可能自己 fork 了子进程）。"""
    if proc is None:
        return
    try:
        if os.name == "posix":
            pgid = os.getpgid(proc.pid)
            # 只杀自己新建的进程组 —— 万一 setsid 失败，绝不能误杀父进程所在组
            if pgid == proc.pid:
                os.killpg(pgid, signal.SIGKILL)
            else:
                proc.kill()
        else:  # pragma: no cover - Windows
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _read_tail(path: str, limit: int = 2000) -> str:
    """读取子进程 stderr 末尾若干字符（用于错误提示）。"""
    try:
        with open(path, "rb") as f:
            try:
                f.seek(-limit, os.SEEK_END)
            except OSError:
                f.seek(0)
            data = f.read()
        return data.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _cleanup_home(home: str) -> None:
    """清理子进程的临时 HOME。"""
    try:
        import shutil
        shutil.rmtree(home, ignore_errors=True)
    except Exception:
        pass
