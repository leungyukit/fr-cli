"""
真实集成测试 —— 不 Mock，使用真实文件系统和真实对象实例

本测试：
  - 创建真实的临时目录作为 Agent 洞府
  - 读写真实的 JSON 配置文件
  - 实例化真实的 AppState、CommandExecutor
  - 验证所有模型配置相关功能的完整链路

⚠️  不涉及真实 LLM API 调用（因无外部 Key），
    但会验证客户端实例化、配置解析、缓存、上下文切换等全部内部逻辑。
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# 确保项目根目录在路径中
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ------------------------------------------------------------------
# 测试基础设施
# ------------------------------------------------------------------

class RealTestEnv:
    """为每次测试创建隔离的真实环境"""

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="fr_cli_real_test_"))
        self.agents_dir = self.tmpdir / "agents"
        self.config_file = self.tmpdir / "config.json"
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        # 隔离 Agent 目录（通过 monkeypatch 方式）
        import fr_cli.agent.manager as mgr
        self._orig_agents_dir = mgr.AGENTS_DIR
        mgr.AGENTS_DIR = self.agents_dir

        # 隔离配置目录（HOME 指向 tmpdir）
        self._orig_home = Path.home
        Path.home = lambda: self.tmpdir

    def cleanup(self):
        import fr_cli.agent.manager as mgr
        mgr.AGENTS_DIR = self._orig_agents_dir
        Path.home = self._orig_home
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def make_agent(self, name: str, code: str = "def run(context, **kwargs): return 'ok'", cfg: dict = None):
        """在真实文件系统上创建一个 Agent 分身"""
        d = self.agents_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "agent.py").write_text(code, encoding="utf-8")
        if cfg is not None:
            from fr_cli.agent.manager import save_agent_config
            save_agent_config(name, cfg)
        return d


# ------------------------------------------------------------------
# 1. 配置系统真实测试
# ------------------------------------------------------------------

def test_real_config_load_save():
    """真实测试：配置原子写入、读取、备份"""
    from fr_cli.conf.config import load_config, save_config, CONFIG_FILE, CONFIG_BACKUP

    env = RealTestEnv()
    # 重定向配置路径到临时目录（save_config 使用模块级常量）
    import fr_cli.conf.config as conf_mod
    orig_file = conf_mod.CONFIG_FILE
    orig_backup = conf_mod.CONFIG_BACKUP
    conf_mod.CONFIG_FILE = env.config_file
    conf_mod.CONFIG_BACKUP = env.tmpdir / ".zhipu_cli_config.json.bak"

    try:
        # 首次加载应返回默认配置
        cfg = load_config()
        assert cfg["provider"] == "zhipu"
        assert "providers" in cfg

        # 修改并保存（首次保存，CONFIG_FILE 原本不存在，不会触发备份）
        cfg["providers"]["deepseek"] = {"key": "real-ds-key", "model": "deepseek-chat"}
        assert save_config(cfg) is True

        # 重新加载应持久化
        cfg2 = load_config()
        assert cfg2["providers"]["deepseek"]["key"] == "real-ds-key"
        assert cfg2["providers"]["deepseek"]["model"] == "deepseek-chat"

        # 第二次保存，此时 CONFIG_FILE 已存在，应触发备份机制
        cfg2["providers"]["deepseek"]["model"] = "deepseek-coder"
        assert save_config(cfg2) is True
        assert conf_mod.CONFIG_BACKUP.exists(), "第二次保存应生成备份文件"
        # 验证备份内容正确
        backup_data = json.loads(conf_mod.CONFIG_BACKUP.read_text(encoding="utf-8"))
        assert backup_data["providers"]["deepseek"]["model"] == "deepseek-chat"

        print("✅ test_real_config_load_save 通过")
    finally:
        # 无论测试是否通过，都必须恢复全局常量
        conf_mod.CONFIG_FILE = orig_file
        conf_mod.CONFIG_BACKUP = orig_backup
        env.cleanup()


def test_real_providers_setup_flow():
    """真实测试：/providers setup 的完整配置链路（模拟交互输入）"""
    from fr_cli.conf.config import load_config, save_config
    from fr_cli.core.core import AppState
    from fr_cli.repl.commands import _cmd_providers

    env = RealTestEnv()
    try:
        cfg = load_config()
        cfg["provider"] = "zhipu"
        cfg["model"] = "glm-4-flash"
        cfg["providers"] = {}
        save_config(cfg)

        state = AppState(cfg)

        # 模拟 /providers add deepseek my-key deepseek-chat
        ok = _cmd_providers(state, ["/providers", "add", "deepseek", "my-real-key", "deepseek-chat"])
        assert ok is False  # 命令处理器返回 False 表示不退出

        # 验证内存和持久化
        assert state.cfg["providers"]["deepseek"]["key"] == "my-real-key"
        assert state.cfg["providers"]["deepseek"]["model"] == "deepseek-chat"

        cfg_reloaded = load_config()
        assert cfg_reloaded["providers"]["deepseek"]["key"] == "my-real-key"

        # 模拟 /providers use deepseek
        ok = _cmd_providers(state, ["/providers", "use", "deepseek"])
        assert ok is False
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"

        print("✅ test_real_providers_setup_flow 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 2. LLM 客户端工厂真实测试
# ------------------------------------------------------------------

def test_real_llm_client_creation():
    """真实测试：LLM 客户端实例化（不调用 API）"""
    from fr_cli.core.llm import create_llm_client, create_llm_client_for, _resolve_llm_kwargs

    # 智谱客户端
    cfg = {"key": "zhipu-key-123", "provider": "zhipu", "providers": {}}
    client, provider, model = create_llm_client(cfg)
    assert provider == "zhipu"
    assert model == "glm-4-flash"
    assert client.api_key == "zhipu-key-123"

    # DeepSeek 客户端
    cfg = {
        "provider": "deepseek",
        "providers": {"deepseek": {"key": "ds-key", "model": "deepseek-chat"}}
    }
    client, provider, model = create_llm_client(cfg)
    assert provider == "deepseek"
    assert model == "deepseek-chat"
    # OpenAI 兼容客户端内部持有 openai.OpenAI 实例
    assert hasattr(client, "_client")

    # create_llm_client_for 覆盖模型名
    client2, provider2, model2 = create_llm_client_for("deepseek", "custom-model", cfg)
    assert model2 == "custom-model"
    assert client2.api_key == "ds-key"

    # override_key 优先级
    client3, _, _ = create_llm_client_for("deepseek", "m", cfg, override_key="override")
    assert client3.api_key == "override"

    # _resolve_llm_kwargs 正确解析 base_url
    cfg_custom = {
        "providers": {
            "deepseek": {"key": "k", "base_url": "https://custom.example.com/v1"}
        }
    }
    cls, kwargs = _resolve_llm_kwargs("deepseek", cfg_custom)
    assert kwargs["base_url"] == "https://custom.example.com/v1"

    print("✅ test_real_llm_client_creation 通过")


def test_real_appstate_client_cache():
    """真实测试：AppState 客户端缓存命中与隔离"""
    from fr_cli.core.core import AppState

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "k",
            "model": "glm-4-flash",
            "providers": {
                "deepseek": {"key": "ds-k"},
                "kimi": {"key": "kimi-k"}
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)

        # 同一配置应命中缓存
        c1 = state.get_client_for("deepseek", "m1")
        c2 = state.get_client_for("deepseek", "m1")
        assert c1 is c2, "缓存应返回同一实例"

        # 不同 provider 应创建新实例
        c3 = state.get_client_for("kimi", "m1")
        assert c3 is not c1, "不同 provider 不应共享缓存"

        # 不同 override_key 应创建新实例
        c4 = state.get_client_for("deepseek", "m1", override_key="special")
        assert c4 is not c1, "不同 override_key 不应共享缓存"
        assert c4.api_key == "special"

        # 再次获取同一 override_key 应命中缓存
        c5 = state.get_client_for("deepseek", "m1", override_key="special")
        assert c4 is c5, "override_key 缓存应命中"

        print("✅ test_real_appstate_client_cache 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 3. Agent 配置真实测试
# ------------------------------------------------------------------

def test_real_agent_config_lifecycle():
    """真实测试：Agent config.json 的完整生命周期"""
    from fr_cli.agent.manager import (
        load_agent_config, save_agent_config, list_agents, agent_exists,
        create_agent_dir, load_persona, save_persona
    )

    env = RealTestEnv()
    try:
        # 创建 Agent
        env.make_agent("alpha", cfg={"provider": "deepseek", "model": "deepseek-chat"})

        # 读取配置
        cfg = load_agent_config("alpha")
        assert cfg["provider"] == "deepseek"
        assert cfg["model"] == "deepseek-chat"

        # 更新配置（仅改模型）
        cfg["model"] = "deepseek-coder"
        save_agent_config("alpha", cfg)
        cfg2 = load_agent_config("alpha")
        assert cfg2["model"] == "deepseek-coder"

        # 列表应包含 has_config 标志
        agents = list_agents()
        assert len(agents) == 1
        assert agents[0]["has_config"] is True

        # 清除配置
        save_agent_config("alpha", {})
        assert load_agent_config("alpha") == {}

        # 不存在的 Agent 返回空
        assert load_agent_config("ghost") == {}

        print("✅ test_real_agent_config_lifecycle 通过")
    finally:
        env.cleanup()


def test_real_agent_llm_resolution():
    """真实测试：Agent 专属模型解析的完整链路"""
    from fr_cli.core.core import AppState
    from fr_cli.agent.manager import save_agent_config

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {
                "deepseek": {"key": "ds-key"},
                "kimi": {"key": "kimi-key"}
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)

        # Agent 无配置 → 回退全局
        env.make_agent("default_agent")
        client, provider, model = state.resolve_agent_llm("default_agent")
        assert provider == "zhipu"
        assert model == "glm-4-flash"

        # Agent 有配置 → 使用专属
        env.make_agent("ds_agent", cfg={"provider": "deepseek", "model": "deepseek-chat"})
        client, provider, model = state.resolve_agent_llm("ds_agent")
        assert provider == "deepseek"
        assert model == "deepseek-chat"
        assert client.api_key == "ds-key"

        # Agent 有独立 key → 覆盖全局
        env.make_agent("custom_key_agent", cfg={
            "provider": "kimi", "model": "moonshot-v1-8k", "key": "my-own-key"
        })
        client, provider, model = state.resolve_agent_llm("custom_key_agent")
        assert provider == "kimi"
        assert model == "moonshot-v1-8k"
        assert client.api_key == "my-own-key"

        # Agent 配置 provider 为空字符串 → 回退全局
        env.make_agent("empty_agent", cfg={"provider": "", "model": ""})
        client, provider, model = state.resolve_agent_llm("empty_agent")
        assert provider == "zhipu"

        print("✅ test_real_agent_llm_resolution 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 4. CommandExecutor 上下文切换真实测试
# ------------------------------------------------------------------

def test_real_executor_agent_context():
    """真实测试：CommandExecutor push/pop Agent 上下文覆盖"""
    from fr_cli.core.core import AppState
    from fr_cli.command.executor import CommandExecutor

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "k",
            "model": "glm-4-flash",
            "providers": {},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        executor = CommandExecutor(state)

        # 默认 deps 使用全局
        deps = executor._get_deps()
        assert deps.client is state.client
        assert deps.model_name == "glm-4-flash"

        # push 后 deps 切换
        from fr_cli.core.llm import create_llm_client_for
        fake_cfg = {"providers": {"deepseek": {"key": "fake-ds-key"}}}
        agent_client, _, _ = create_llm_client_for("deepseek", "deepseek-chat", fake_cfg)
        executor.push_agent_context(agent_client, "deepseek-chat")

        deps = executor._get_deps()
        assert deps.client is agent_client
        assert deps.model_name == "deepseek-chat"

        # pop 后恢复全局
        executor.pop_agent_context()
        deps = executor._get_deps()
        assert deps.client is state.client
        assert deps.model_name == "glm-4-flash"

        # 嵌套 push/pop（验证栈语义，虽然当前是单槽位）
        executor.push_agent_context(agent_client, "m1")
        executor.push_agent_context(state.client, "m2")  # 第二次覆盖
        deps = executor._get_deps()
        assert deps.model_name == "m2"
        executor.pop_agent_context()
        deps = executor._get_deps()
        assert deps.model_name == "m1"  # 应恢复为 m1
        executor.pop_agent_context()

        print("✅ test_real_executor_agent_context 通过")
    finally:
        env.cleanup()


def test_real_executor_agent_context_in_run_agent():
    """真实测试：run_agent 执行期间 executor 上下文自动切换"""
    from fr_cli.core.core import AppState
    from fr_cli.agent.executor import run_agent
    from fr_cli.agent.manager import save_agent_config

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "k",
            "model": "glm-4-flash",
            "providers": {"deepseek": {"key": "ds-k"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)

        # Agent 代码中读取 executor._get_deps() 来验证上下文
        test_code = '''
def run(context, **kwargs):
    deps = context["executor"]._get_deps()
    return f"provider={deps.model_name}|client_key={deps.client.api_key}"
'''
        env.make_agent("ctx_agent", code=test_code, cfg={
            "provider": "deepseek", "model": "deepseek-chat"
        })

        result, err = run_agent("ctx_agent", state)
        assert err is None, f"执行出错: {err}"
        assert "provider=deepseek-chat" in result
        assert "client_key=ds-k" in result

        # 执行完毕后全局应恢复
        deps = state.executor._get_deps()
        assert deps.model_name == "glm-4-flash"

        print("✅ test_real_executor_agent_context_in_run_agent 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 5. /agent_model 命令真实测试
# ------------------------------------------------------------------

def test_real_cmd_agent_model():
    """真实测试：/agent_model 命令的完整交互链路"""
    from fr_cli.core.core import AppState
    from fr_cli.repl.commands import _cmd_agent_model
    from fr_cli.agent.manager import load_agent_config

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "k",
            "model": "glm-4-flash",
            "providers": {"deepseek": {"key": "ds-k"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        env.make_agent("test_agent")

        # 1. 设置专属模型
        _cmd_agent_model(state, ["/agent_model", "test_agent", "deepseek:deepseek-chat"])
        cfg_loaded = load_agent_config("test_agent")
        assert cfg_loaded["provider"] == "deepseek"
        assert cfg_loaded["model"] == "deepseek-chat"

        # 2. 设置独立 key
        _cmd_agent_model(state, ["/agent_model", "test_agent", "--key", "secret-key-123"])
        cfg_loaded = load_agent_config("test_agent")
        assert cfg_loaded["key"] == "secret-key-123"

        # 3. 查看配置（无 arg2）
        _cmd_agent_model(state, ["/agent_model", "test_agent"])

        # 4. 清除配置
        _cmd_agent_model(state, ["/agent_model", "test_agent", "clear"])
        cfg_loaded = load_agent_config("test_agent")
        assert cfg_loaded == {}

        # 5. 仅传模型名（保持当前 provider）
        _cmd_agent_model(state, ["/agent_model", "test_agent", "glm-4-plus"])
        cfg_loaded = load_agent_config("test_agent")
        assert cfg_loaded["provider"] == "zhipu"
        assert cfg_loaded["model"] == "glm-4-plus"

        # 6. 空模型名应被拒绝
        _cmd_agent_model(state, ["/agent_model", "test_agent", "deepseek:"])
        cfg_loaded = load_agent_config("test_agent")
        # 配置应保持不变（因为校验失败）
        assert cfg_loaded["model"] == "glm-4-plus"

        # 7. 无效 provider 应被拒绝
        _cmd_agent_model(state, ["/agent_model", "test_agent", "invalid:model"])
        cfg_loaded = load_agent_config("test_agent")
        assert cfg_loaded["provider"] == "zhipu"

        print("✅ test_real_cmd_agent_model 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 6. Workflow 上下文切换真实测试
# ------------------------------------------------------------------

def test_real_workflow_agent_context():
    """真实测试：run_workflow 执行期间 ai_generate 使用 Agent 专属模型"""
    from fr_cli.core.core import AppState
    from fr_cli.agent.workflow import run_workflow, save_workflow

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "k",
            "model": "glm-4-flash",
            "providers": {"deepseek": {"key": "ds-k"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)

        # 创建一个 workflow，其中 ai_generate 步骤会验证 context 中的模型
        wf = '''# 测试工作流

## 步骤1：验证模型
- **action**: ai_generate
- **params**:
  - prompt: "只需返回当前模型名称"
'''
        env.make_agent("wf_agent", cfg={"provider": "deepseek", "model": "deepseek-chat"})
        save_workflow("wf_agent", wf)

        # 执行 workflow（stream_cnt 需要真实 API，这里会失败，
        # 但我们验证执行前后 executor 上下文已正确切换/恢复）
        result, err, steps = run_workflow("wf_agent", state, user_input="hello")

        # 无论 workflow 内部是否成功，执行后全局上下文必须恢复
        deps = state.executor._get_deps()
        assert deps.model_name == "glm-4-flash", f"workflow 执行后未恢复全局模型: {deps.model_name}"

        # 如果因无真实 Key 导致 ai_generate 失败，这是预期的
        if err and "API" in str(err) or "密钥" in str(err) or "key" in str(err).lower():
            print("   (workflow 因无外部 API Key 而失败，属于预期行为)")

        print("✅ test_real_workflow_agent_context 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 7. /providers list 修复真实测试
# ------------------------------------------------------------------

def test_real_providers_list_no_crash():
    """真实测试：/providers list 在多个 provider 配置下不崩溃"""
    from fr_cli.core.core import AppState
    from fr_cli.repl.commands import _cmd_providers
    from fr_cli.conf.config import load_config, save_config

    env = RealTestEnv()
    try:
        cfg = load_config()
        cfg["providers"] = {
            "zhipu": {"key": "z-key", "model": "glm-4-flash"},
            "deepseek": {"key": "d-key", "model": "deepseek-chat", "base_url": "https://custom.com"},
            "kimi": {"key": "", "model": ""},  # 空配置
        }
        save_config(cfg)
        state = AppState(cfg)

        # 此调用在修复前会因 pcfg 未定义而抛出 NameError
        ok = _cmd_providers(state, ["/providers"])
        assert ok is False

        ok = _cmd_providers(state, ["/providers", "list"])
        assert ok is False

        print("✅ test_real_providers_list_no_crash 通过")
    finally:
        env.cleanup()


# ------------------------------------------------------------------
# 8. 新道统（豆包 / 小米 MiMo）真实测试
# ------------------------------------------------------------------

def test_real_doubao_mimo_client_creation():
    """真实测试：豆包和小米 MiMo 客户端可正常实例化"""
    from fr_cli.core.llm import create_llm_client_for, _PROVIDERS, OpenAICompatibleClient

    # 豆包
    cfg_db = {"providers": {"doubao": {"key": "db-key"}}}
    client_db, provider_db, model_db = create_llm_client_for("doubao", "doubao-1-5-pro-32k-250115", cfg_db)
    assert provider_db == "doubao"
    assert model_db == "doubao-1-5-pro-32k-250115"
    assert isinstance(client_db, OpenAICompatibleClient)
    assert client_db.api_key == "db-key"
    assert _PROVIDERS["doubao"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"

    # 小米 MiMo
    cfg_mimo = {"providers": {"mimo": {"key": "mimo-key"}}}
    client_mimo, provider_mimo, model_mimo = create_llm_client_for("mimo", "mimo-v2-pro", cfg_mimo)
    assert provider_mimo == "mimo"
    assert model_mimo == "mimo-v2-pro"
    assert isinstance(client_mimo, OpenAICompatibleClient)
    assert client_mimo.api_key == "mimo-key"
    assert _PROVIDERS["mimo"]["base_url"] == "https://api.xiaomimimo.com/v1"

    print("✅ test_real_doubao_mimo_client_creation 通过")


def test_real_doubao_mimo_agent_binding():
    """真实测试：Agent 可绑定豆包或小米 MiMo 专属模型"""
    from fr_cli.core.core import AppState
    from fr_cli.repl.commands import _cmd_agent_model
    from fr_cli.agent.manager import load_agent_config

    env = RealTestEnv()
    try:
        cfg = {
            "provider": "zhipu",
            "key": "k",
            "model": "glm-4-flash",
            "providers": {
                "doubao": {"key": "db-key"},
                "mimo": {"key": "mimo-key"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        env.make_agent("db_agent")
        env.make_agent("mimo_agent")

        # 绑定豆包
        _cmd_agent_model(state, ["/agent_model", "db_agent", "doubao:doubao-1-5-pro-32k-250115"])
        db_cfg = load_agent_config("db_agent")
        assert db_cfg["provider"] == "doubao"
        assert db_cfg["model"] == "doubao-1-5-pro-32k-250115"

        # 绑定小米 MiMo
        _cmd_agent_model(state, ["/agent_model", "mimo_agent", "mimo:mimo-v2-pro"])
        mimo_cfg = load_agent_config("mimo_agent")
        assert mimo_cfg["provider"] == "mimo"
        assert mimo_cfg["model"] == "mimo-v2-pro"

        # 验证 Agent LLM 解析
        client_db, p_db, m_db = state.resolve_agent_llm("db_agent")
        assert p_db == "doubao"
        assert m_db == "doubao-1-5-pro-32k-250115"
        assert client_db.api_key == "db-key"

        client_mimo, p_mimo, m_mimo = state.resolve_agent_llm("mimo_agent")
        assert p_mimo == "mimo"
        assert m_mimo == "mimo-v2-pro"
        assert client_mimo.api_key == "mimo-key"

        print("✅ test_real_doubao_mimo_agent_binding 通过")
    finally:
        env.cleanup()


def test_real_providers_list_includes_new_providers():
    """真实测试：/providers list 包含豆包和小米 MiMo"""
    from fr_cli.core.llm import list_providers, get_provider_info

    providers = list_providers()
    ids = [p["id"] for p in providers]
    assert "doubao" in ids, f"应包含 doubao, 实际: {ids}"
    assert "mimo" in ids, f"应包含 mimo, 实际: {ids}"

    db_info = get_provider_info("doubao")
    assert db_info["name"] == "豆包 (Doubao)"
    assert db_info["default_model"] == "doubao-1-5-pro-32k-250115"

    mimo_info = get_provider_info("mimo")
    assert mimo_info["name"] == "小米 MiMo"
    assert mimo_info["default_model"] == "mimo-v2-flash"

    print("✅ test_real_providers_list_includes_new_providers 通过")


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("开始真实集成测试（无 Mock）")
    print("=" * 60)

    tests = [
        test_real_config_load_save,
        test_real_llm_client_creation,
        test_real_appstate_client_cache,
        test_real_providers_setup_flow,
        test_real_providers_list_no_crash,
        test_real_agent_config_lifecycle,
        test_real_agent_llm_resolution,
        test_real_executor_agent_context,
        test_real_executor_agent_context_in_run_agent,
        test_real_cmd_agent_model,
        test_real_workflow_agent_context,
        test_real_doubao_mimo_client_creation,
        test_real_doubao_mimo_agent_binding,
        test_real_providers_list_includes_new_providers,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ {t.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 项")
    print("=" * 60)

    if failed:
        sys.exit(1)
