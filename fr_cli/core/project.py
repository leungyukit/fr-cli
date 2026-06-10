"""
项目级配置加载 —— 让 fr-cli 感知当前项目

扫描规则（优先级从高到低）：
1. .fr-cli/persona.md —— 项目专属人设（注入到 system prompt）
2. .fr-cli/agents/ —— 项目专属 Agent（临时挂载）
3. .fr-cli/MANUAL.md —— 项目专属使用文档
4. .fr-cli/config.json —— 项目级配置覆盖

加载时机：每次进入主循环检查 cwd（轻量级，只检查文件存在）
"""
import os
from pathlib import Path
from typing import Optional, Dict, List


PROJECT_DIR_NAME = ".fr-cli"


def find_project_root(start_dir: Optional[str] = None) -> Optional[Path]:
    """向上查找包含 .fr-cli/ 的项目根目录

    Args:
        start_dir: 起始目录（None 用 cwd）
    Returns:
        找到的 .fr-cli 目录路径，未找到返回 None
    """
    cur = Path(start_dir or os.getcwd()).resolve()
    # 最多向上查 5 层（避免 / 目录扫描太久）
    for _ in range(5):
        candidate = cur / PROJECT_DIR_NAME
        if candidate.is_dir():
            return candidate
        parent = cur.parent
        if parent == cur:  # 已到根目录
            break
        cur = parent
    return None


def load_project_persona(project_root: Path) -> Optional[str]:
    """加载项目 persona.md，返回内容"""
    p = project_root / "persona.md"
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def list_project_agents(project_root: Path) -> List[str]:
    """列出项目下的 Agent 名称（子目录名）"""
    agents_dir = project_root / "agents"
    if not agents_dir.is_dir():
        return []
    return [d.name for d in agents_dir.iterdir() if d.is_dir()]


def load_project_manual(project_root: Path) -> Optional[str]:
    """加载项目 .fr-cli/MANUAL.md（如存在）"""
    p = project_root / ".fr-cli" / "MANUAL.md"
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def load_project_config(project_root: Path) -> Dict:
    """加载项目 config.json（轻量级覆盖）"""
    import json
    p = project_root / "config.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ==================== 初始化项目目录模板 ====================

PERSONA_TEMPLATE = """# {project_name} 项目人设

> 这是项目级 persona，会注入到 fr-cli 的 system prompt。
> 每次进入项目目录时自动加载，无需手动指定。

## 项目背景
（描述这个项目是什么、解决什么问题、目标用户是谁）

## 编码规范
- （命名规范 / 缩进 / 引号风格）
- （错误处理偏好：异常 vs 返回值）
- （注释语言：中文 / 英文）

## 常用技术栈
- （语言 / 框架 / 关键依赖）

## AI 行为偏好
- 回答用中文 / 英文
- 改代码时先解释思路还是直接给代码
- 测试驱动还是先实现后补测试
- 是否接受 type hints

## 注意事项
- （不要碰的目录 / 不要用的库 / 历史包袱）
"""


AGENT_TEMPLATE_DIR = """# {agent_name}（项目级 Agent）

> 项目级 Agent：跟随项目走，不放进全局 ~/.fr_cli/agents/

## 角色
（这个 Agent 负责什么）

## 工作流
1. 第一步：...
2. 第二步：...
"""


def init_project(project_name: str = None, target_dir: str = None) -> str:
    """在指定目录创建 .fr-cli/ 模板（persona.md + agents/ + config.json）

    Returns:
        创建的 .fr-cli/ 路径
    """
    target = Path(target_dir or os.getcwd()) / PROJECT_DIR_NAME
    if target.exists():
        return f"⚠️ 目录已存在: {target}"

    target.mkdir(parents=True, exist_ok=True)
    (target / "agents").mkdir(exist_ok=True)
    (target / "logs").mkdir(exist_ok=True)

    name = project_name or target.parent.name
    (target / "persona.md").write_text(
        PERSONA_TEMPLATE.format(project_name=name), encoding="utf-8"
    )
    (target / "agents" / "_example").mkdir(exist_ok=True)
    (target / "agents" / "_example" / "persona.md").write_text(
        AGENT_TEMPLATE_DIR.format(agent_name="_example"), encoding="utf-8"
    )
    (target / "config.json").write_text(
        '{\n  "lang": "zh",\n  "auto_load_persona": true\n}\n', encoding="utf-8"
    )

    return f"✅ 已创建项目目录: {target}\n   ├── persona.md\n   ├── agents/_example/\n   └── config.json"


# ==================== 项目上下文注入 ====================

def build_project_context_injection(state) -> str:
    """构建项目上下文注入字符串（追加到 system prompt）"""
    proj_root = find_project_root(state.vfs.cwd if hasattr(state, "vfs") else None)
    if not proj_root:
        return ""

    parts = ["\n\n[项目级上下文]"]
    parts.append(f"📁 项目根: {proj_root.parent}")

    persona = load_project_persona(proj_root)
    if persona:
        parts.append(f"\n## 项目 Persona\n{persona[:2000]}")

    agents = list_project_agents(proj_root)
    if agents:
        parts.append(f"\n## 项目 Agent: {', '.join(agents)}")

    proj_cfg = load_project_config(proj_root)
    if proj_cfg:
        parts.append(f"\n## 项目配置: {proj_cfg}")

    return "\n".join(parts)
