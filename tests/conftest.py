# -*- coding: utf-8 -*-
"""pytest 全局 HOME 隔离 —— 跑测试永不污染真实的 ``~/.fr_cli/``。

背景
----
fr-cli 的测试默认把状态写进用户级目录：cron 固件、gatekeeper 持久化、
wizard 标志位、``usage.json`` 全都落在 ``~/.fr_cli/``。仓库原先没有任何
隔离机制，于是任何人跑一次不带 ``HOME=`` 重定向的 ``pytest tests/``，就会：

* 把 ``echo hello`` / ``echo x`` 之类的测试 cron 任务写进真实配置；
* 清空 ``providers``，丢掉 ``model`` / ``provider`` / ``hermes`` /
  ``gatekeeper`` / ``context`` 等键，``start_wizard_done`` 被翻回 False。

2026-11-24 实测过一次：33 键掉到 27 键，还多出两个每分钟执行的垃圾任务。

为什么必须在导入期做，而不是用 fixture
------------------------------------
``fr_cli/conf/paths.py`` 在模块导入时就把 ``ROOT`` 固定为
``Path.home() / ".fr_cli"``。autouse fixture 要等测试模块收集完之后才跑，
那时候 ROOT 已经钉死在真实 HOME 上了，再改环境变量也无效。本文件由 pytest
在导入 ``tests/`` 下任何测试模块**之前**加载，是唯一够早的时机。

行为
----
* ``HOME`` / ``USERPROFILE`` 被指到一个临时目录，测试全部落在那里。
* 如果外部已经把 HOME 重定向到系统临时目录（开发者或 CI 自己设了
  ``HOME=/tmp/xxx``），尊重之，不覆盖、也不删。
* 只有本文件自己创建的目录才会在进程退出时清理。
"""

import atexit
import os
import shutil
import tempfile

import pytest

_ISOLATED_HOME = None
_OWNED = False


def _redirect_home():
    """把 HOME 指到临时目录并返回该路径；重复调用是幂等的。"""
    global _ISOLATED_HOME, _OWNED
    if _ISOLATED_HOME is not None:
        return _ISOLATED_HOME

    real_home = os.path.expanduser("~")
    current = os.environ.get("HOME") or real_home
    tmp_root = os.path.abspath(tempfile.gettempdir())

    # 外部已重定向到临时目录 → 尊重，且不负责清理
    if current != real_home and os.path.abspath(current).startswith(tmp_root):
        _ISOLATED_HOME = current
        _OWNED = False
    else:
        _ISOLATED_HOME = tempfile.mkdtemp(prefix="fr_cli_pytest_home_")
        _OWNED = True

    os.environ["HOME"] = _ISOLATED_HOME
    os.environ["USERPROFILE"] = _ISOLATED_HOME  # Windows 下 expanduser 用这个

    if _OWNED:
        atexit.register(_cleanup, _ISOLATED_HOME)
    return _ISOLATED_HOME


def _cleanup(path):
    """进程退出时删掉自己创建的临时 HOME；有进程占用就静默跳过。"""
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# 导入即执行 —— 必须早于 tests/ 下任何测试模块导入 fr_cli
# ---------------------------------------------------------------------------
ISOLATED_HOME = _redirect_home()


def pytest_report_header(config):
    """在 pytest 头部显示隔离状态，便于确认隔离真的生效。"""
    return "fr-cli 测试隔离 HOME=%s%s" % (
        ISOLATED_HOME, "" if _OWNED else " (外部提供)"
    )


# ===================================================================
# eval 层 fixture（P2-1 / P2-2）
#
# 上面那份文件级 HOME 重定向已经保证"跑测试不碰真实 ~/.fr_cli"。
# 这一段补的是**单测粒度**的隔离件：
#   - tmp_home        每个测试一个独立 HOME（并把 paths.ROOT 一并指过去）
#   - isolated_cfg    干净的 config 字典（不读写用户真实 config.json）
#   - scripted_llm    脚本化 LLM（零网络、可编排多步响应）
# ===================================================================


@pytest.fixture
def tmp_home(monkeypatch, tmp_path):
    """把 HOME 与 ``~/.fr_cli`` 根目录指向临时目录。

    仅改环境变量是不够的 —— ``fr_cli.conf.paths`` 的路径在**导入期**就固定了，
    所以这里额外改 ``paths._root_holder.value``（所有动态路径的**根源**）。

    ⚠️ 顺序很重要（v2.8.7 修）：**必须先 import，再改路径**。

    ``fr_cli/conf/config.py`` 与 ``fr_cli/conf/__init__.py`` 在 import 期
    ``from fr_cli.conf.paths import CONFIG_FILE`` **按值冻结**了路径常量。
    若先改了 ``paths.CONFIG_FILE``（动态属性）再首次 import 这两个模块，
    它们会把**临时目录**永久冻进模块常量 —— fixture 结束后，
    所有后续用例都写进一个已被 pytest 删除的临时目录，
    于是 cron / notifier / gatekeeper / m365 等持久化用例连环失败。

    同理，这里改的是 ``_root_holder.value``（根源）而不是
    ``paths.ROOT`` / ``paths.CONFIG_FILE``（派生属性）——
    改派生属性会在模块里留下**冻结的属性**，从此不再跟随根源变化。

    诚实边界：模块里写死 ``from fr_cli.conf.paths import XXX`` 的地方拿到的
    仍是导入期绑定值 —— 但那已经是本文件顶部重定向过的临时 HOME 了，
    绝不会指向用户真实 HOME。真正"动态解析"的路径（``paths.XXX``）才会被
    这里的 monkeypatch 改到本测试专属的目录。

    Returns:
        Path: 临时 HOME 目录
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    root = home / ".fr_cli"
    root.mkdir(parents=True, exist_ok=True)

    # ① 先 import —— 让这两个模块在"路径还没被改"的状态下冻结自己的常量，
    #    这样 monkeypatch 还原时拿到的旧值是正确��
    from fr_cli.conf import config as _config
    from fr_cli.conf import paths as _paths

    # ② 改**根源** —— paths.XXX 全部动态跟随，不需要逐个 patch
    monkeypatch.setattr(_paths._root_holder, "value", root)

    # ③ 按值冻结的副本也一并改（conf.config 在导入期复制了同一批常量）
    monkeypatch.setattr(_config, "ROOT", root, raising=False)
    monkeypatch.setattr(_config, "CONFIG_FILE", root / "config.json", raising=False)
    monkeypatch.setattr(_config, "CONFIG_BACKUP", root / "config.json.bak", raising=False)

    return home


@pytest.fixture
def isolated_cfg(tmp_home):
    """一份干净的配置字典 —— 不污染用户真实的 ``~/.fr_cli/config.json``。

    默认走 ``manual`` 自治模式（安全确认必须真的问），不预置任何 API Key。

    Returns:
        dict: 可直接塞给 ``AppState(cfg)`` 的配置
    """
    return {
        "version": 3,
        "lang": "zh",
        "limit": 4096,
        "allowed_dirs": [],
        "aliases": {},
        "auto_confirm": {},
        "autonomous_mode": "manual",
        "thinking_mode": "direct",
        "providers": {},
        "mail": {},
        "disk": {},
        "mcp": {"servers": []},
    }


@pytest.fixture
def scripted_llm():
    """脚本化 LLM 客户端 —— 零网络，可编排多步响应。

    用法::

        client = scripted_llm
        client.push("第一轮回复")
        client.on("关键词", "命中关键词的回复")

    Returns:
        ScriptedMockClient: 脚本化 mock 客户端
    """
    from fr_cli.core.llm.mock import ScriptedMockClient

    return ScriptedMockClient()


@pytest.fixture
def eval_workdir(tmp_path):
    """eval 用的沙盒工作目录 —— VFS 会把它当作唯一允许写入的根。

    Returns:
        Path: 工作目录（已创建）
    """
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


# ===================================================================
# 跨用例污染闸门：定时任务计时器
#
# 定时任务的计时器是 threading.Timer 后台线程，daemon=True 所以进程退出
# 时不会挡住收尾 —— 但**在进程存活期间**它会继续触发。而每次触发都会
# 进入 fr_cli/weapon/cron.py 的 _stdout_guard()：
# prompt_toolkit.patch_stdout 是**进程级**的 sys.stdout 替换，会把此刻
# 其它线程/用例的 print 全部劫持走。
#
# 症状极具迷惑性：某个用例单跑通过、全量跑时随机失败，且失败信息是
# "断言输出为空"而不是任何异常。实测案例：
# tests/test_plugin_exec.py::test_exec_plugin_unicode_name
# —— 用例创建的 interval=10s 定时任务在整套测试跑到一半时触发，
# 正好撞上这个用例的 capsys 断言。
#
# 这里的闸门在**每个用例结束后**把残留计时器一次收干净，污染窗口归零。
# ===================================================================


@pytest.fixture(autouse=True)
def _stop_cron_timers():
    """每个用例结束后停掉残留的定时任务计时器。

    必须在用例**结束后**执行：夹具 teardown 发生在用例主体之后，
    此时该用例可能刚创建了带计时的 CronManager。
    """
    yield
    try:
        from fr_cli.weapon.cron import stop_all
        stop_all()
    except Exception:
        pass
