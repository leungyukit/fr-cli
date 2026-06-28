"""
Ollama 本地 LLM 工具:
- ollama_status: 检查状态 + 列出模型
- ollama_pull: 下载模型(流式)
- ollama_rm: 删除模型
- ollama_use: 切换当前 provider 到 ollama + 指定 model
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


def _get_ollama_url():
    """从 config 获取 ollama URL"""
    try:
        from fr_cli.conf.config import load_config
        cfg = load_config()
        return cfg.get("ollama_url") or "http://localhost:11434"
    except Exception:
        return "http://localhost:11434"


@register(
    name="ollama_status",
    triggers=["ollama 状态", "ollama status", "本地模型"],
    description="检查 Ollama 是否运行,列出已下载模型",
    params={"url": str},
    aliases=["/ollama_status", "/ollama"],
)
def _register_ollama_status(deps, **kwargs):
    url = kwargs.get("url") or _get_ollama_url()
    from fr_cli.weapon.ollama import format_status
    return Result.ok(format_status(base_url=url))


@register(
    name="ollama_pull",
    triggers=["ollama 下载", "ollama pull"],
    description="下载 Ollama 模型(流式,显示进度)",
    params={"model": str, "url": str},
    aliases=["/ollama_pull"],
)
def _register_ollama_pull(deps, **kwargs):
    model = kwargs.get("model") or ""
    url = kwargs.get("url") or _get_ollama_url()

    if not model:
        return Result.fail("需要提供模型名(如 llama3.2 / qwen2.5 / codellama)")

    from fr_cli.weapon.ollama import pull_model

    print(f"⏳ 正在下载 {model}...")
    lines = []
    last_status = ""
    for chunk in pull_model(model, base_url=url):
        if chunk.get("error"):
            return Result.fail(f"下载失败: {chunk['error']}")
        status = chunk.get("status", "")
        completed = chunk.get("completed", 0)
        total = chunk.get("total", 0)

        if status and status != last_status:
            lines.append(f"  [{status}]")
            last_status = status

        if total > 0 and completed > 0:
            percent = completed / total * 100
            bar_len = 30
            filled = int(bar_len * percent / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"  [{bar}] {percent:.1f}%")

    return Result.ok(f"✅ 模型 {model} 下载完成\n\n" + "\n".join(lines))


@register(
    name="ollama_rm",
    triggers=["ollama 删除", "ollama rm"],
    description="删除本地 Ollama 模型",
    params={"model": str, "url": str},
    aliases=["/ollama_rm"],
)
def _register_ollama_rm(deps, **kwargs):
    model = kwargs.get("model") or ""
    url = kwargs.get("url") or _get_ollama_url()

    if not model:
        return Result.fail("需要提供模型名")

    from fr_cli.weapon.ollama import delete_model
    r = delete_model(model, base_url=url)
    if not r["ok"]:
        return Result.fail(r.get("error", "删除失败"))
    return Result.ok(f"✅ 模型 {model} 已删除")


@register(
    name="ollama_use",
    triggers=["切换 ollama", "use ollama"],
    description="切换当前 provider 到 ollama + 指定 model",
    params={"model": str},
    aliases=["/ollama_use"],
)
def _register_ollama_use(deps, **kwargs):
    model = kwargs.get("model") or "llama3.2"

    try:
        from fr_cli.conf.config import load_config, save_config
        cfg = load_config()
        cfg["provider"] = "ollama"
        cfg["model"] = model
        # Ollama 不需要 API key,但 OpenAI 客户端要求非空
        cfg["providers"] = cfg.get("providers") or {}
        cfg["providers"]["ollama"] = {
            "key": "ollama",
            "model": model,
            "base_url": cfg.get("ollama_url", "http://localhost:11434/v1"),
        }
        save_config(cfg)

        # 重新初始化 client
        if hasattr(deps.state, "reinit_client"):
            deps.state.reinit_client()
        return Result.ok(
            f"✅ 已切换到 Ollama:\n"
            f"  provider: ollama\n"
            f"  model: {model}\n\n"
            f"💡 提示:确保 ollama serve 在后台运行,且已 ollama pull {model}"
        )
    except Exception as e:
        return Result.fail(f"切换失败: {e}")
