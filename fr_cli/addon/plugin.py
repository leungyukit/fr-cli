"""
插件进化引擎
负责本地技能的扫描、动态落盘与沙盒执行
"""
import os, re, subprocess, sys
from pathlib import Path
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import RED, GREEN, DIM, RESET

PLUGIN_DIR = Path.home() / ".zhipu_cli_plugins"

def init_plugins():
    """扫描并初始化本地插件字典 {名字: 绝对路径}"""
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    plugins = {}
    for f in PLUGIN_DIR.glob("*.py"):
        name = f.stem.lower()
        plugins[name] = str(f)
    return plugins

def extract_code(text):
    """提取 AI 回复中的首段 Python 代码段"""
    pattern = r"```python\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def exec_plugin(name, path, args, lang):
    """
    在子进程中安全执行插件
    约定：插件必须包含 def run(args='')
    """
    # 安全检查：插件名必须是合法 Python 标识符
    if not name.isidentifier():
        print(f"{RED}❌ 非法插件名: {name}{RESET}")
        return

    import json, shlex
    # 使用 json.dumps 安全序列化参数，防止字符串逃逸注入
    safe_args = json.dumps(args)
    runner_code = f"""
import sys, json, runpy
sys.path.insert(0, {shlex.quote(str(PLUGIN_DIR))})
mod = runpy.run_module({shlex.quote(name)}, run_name='__main__')
run_fn = mod.get('run')
if run_fn is None:
    print("Error: 插件缺少 run 函数", file=sys.stderr)
else:
    try:
        print(run_fn(json.loads({safe_args})))
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)
"""
    try:
        # 使用子进程执行，限制超时时间为 15 秒
        res = subprocess.run(
            [sys.executable, "-c", runner_code],
            capture_output=True, text=True, timeout=15
        )
        if res.stdout.strip():
            print(res.stdout.strip())
        if res.stderr.strip():
            print(f"{DIM}{res.stderr.strip()}{RESET}")
    except subprocess.TimeoutExpired:
        print(f"{RED}⏳ {T('err_posix', lang)} Timeout (15s){RESET}")
    except Exception as e:
        print(f"{RED}{T('err_posix', lang)} {e}{RESET}")