"""
Skill 系统 —— 让用户定义可复用技能

类似 Claude Code 的 skills:用户写一个 .md 文件描述 skill,包含
- name: skill 名
- description: 触发描述
- steps: 执行步骤(自然语言,AI 解析后调用工具)

存储位置:
  - 用户级: ~/.fr_cli/skills/<name>.md
  - 项目级: .fr_cli/skills/<name>.md(优先)

触发方式:
  - /skill <name>  → 加载并执行
  - 自然语言匹配 description → AI 主动调用

skill 文件格式(Markdown frontmatter):
---
name: code-review
description: 审查代码质量
triggers:
  - 审查代码
  - code review
  - 帮我看看代码
steps: |
  1. 列出当前目录的 Python 文件
  2. 逐个 read_file 读取
  3. 用 ai_generate 总结每个文件的问题
  4. 生成 Markdown 格式的审查报告
---
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any


SKILL_USER_DIR = Path.home() / ".fr_cli" / "skills"
SKILL_PROJECT_DIRNAME = Path(".fr_cli") / "skills"


def _ensure_user_dir():
    SKILL_USER_DIR.mkdir(parents=True, exist_ok=True)


def _parse_frontmatter(content: str) -> Dict[str, Any]:
    """解析 Markdown frontmatter (--- ... ---)

    支持三种值类型:
    - 标量: name: foo
    - 列表: triggers: \\n  - a \\n  - b
    - 多行字符串: steps: | \\n  1. step \\n  2. step
    """
    if not content.startswith("---"):
        return {}

    end = content.find("---", 3)
    if end == -1:
        return {}

    fm = content[3:end].strip()
    result = {}

    # 先按空行分块
    lines = fm.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue

        # key: value 形式
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()

            if val and val not in ("|", ">"):  # 标量
                result[key] = val.strip('"').strip("'")
                i += 1
            elif i + 1 < len(lines) and lines[i + 1].lstrip().startswith("- "):
                # 列表
                items = []
                i += 1
                while i < len(lines) and lines[i].lstrip().startswith("- "):
                    item = lines[i].lstrip()[2:].strip().strip('"').strip("'")
                    items.append(item)
                    i += 1
                result[key] = items
            else:
                # 多行字符串(|  或 >  或空值)
                lines_list = []
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip()
                    # 如果是新的 key:value(没缩进,且非空),停止
                    if next_line and not next_line.startswith(" ") and ":" in next_line \
                            and not next_line.startswith("-"):
                        break
                    if next_line:  # 跳过空行
                        lines_list.append(next_line.lstrip())
                    i += 1
                result[key] = "\n".join(lines_list).strip()
        else:
            # 不应到这里,跳过
            i += 1

    return result


class Skill:
    """单个 Skill 定义"""

    def __init__(self, name: str, description: str, triggers: List[str],
                 steps: str, body: str = "", source_path: Optional[str] = None):
        self.name = name
        self.description = description
        self.triggers = triggers or []
        self.steps = steps or ""
        self.body = body
        self.source_path = source_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "steps": self.steps,
            "source_path": self.source_path,
        }

    def __repr__(self):
        return f"<Skill {self.name} ({len(self.triggers)} triggers)>"


def load_skill_file(path: Path) -> Optional[Skill]:
    """从一个 .md 文件加载 skill"""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    fm = _parse_frontmatter(content)

    # body 是 frontmatter 之后的内容
    body_start = content.find("---", 3)
    body = content[body_start + 3:].strip() if body_start != -1 else ""

    name = fm.get("name") or path.stem
    description = fm.get("description", "")
    triggers = fm.get("triggers", [])
    if isinstance(triggers, str):
        triggers = [triggers]

    steps = fm.get("steps", "")
    if not steps:
        steps = body  # 用整个 body 当步骤

    return Skill(
        name=name,
        description=description,
        triggers=triggers,
        steps=steps,
        body=body,
        source_path=str(path),
    )


def discover_skills(cwd: Optional[Path] = None) -> List[Skill]:
    """发现所有可用的 skills(项目级优先,然后用户级)"""
    skills = []
    seen_names = set()

    # 1. 项目级(优先)
    if cwd:
        project_dir = Path(cwd).resolve() / SKILL_PROJECT_DIRNAME
        if project_dir.exists():
            for f in sorted(project_dir.glob("*.md")):
                skill = load_skill_file(f)
                if skill and skill.name not in seen_names:
                    skills.append(skill)
                    seen_names.add(skill.name)

    # 2. 用户级(全局)
    _ensure_user_dir()
    for f in sorted(SKILL_USER_DIR.glob("*.md")):
        skill = load_skill_file(f)
        if skill and skill.name not in seen_names:
            skills.append(skill)
            seen_names.add(skill.name)

    return skills


def find_skill_by_name(name: str, cwd: Optional[Path] = None) -> Optional[Skill]:
    """按名称查找 skill"""
    skills = discover_skills(cwd)
    for s in skills:
        if s.name == name:
            return s
    return None


def find_skill_by_trigger(text: str, cwd: Optional[Path] = None) -> Optional[Skill]:
    """按触发词匹配 skill"""
    text_lower = text.lower()
    skills = discover_skills(cwd)
    for s in skills:
        for trig in s.triggers:
            if trig.lower() in text_lower:
                return s
    return None


def list_skills(cwd: Optional[Path] = None) -> str:
    """列出所有 skills 的简短描述"""
    skills = discover_skills(cwd)
    if not skills:
        return "暂无 skill。在 ~/.fr_cli/skills/ 或项目 .fr_cli/skills/ 下添加 .md 文件。"

    lines = [f"可用 skills (共 {len(skills)} 个):"]
    for s in skills:
        trigs = ", ".join(s.triggers[:3])
        lines.append(f"  - **{s.name}**: {s.description}")
        if trigs:
            lines.append(f"    触发词: {trigs}")
    return "\n".join(lines)


def install_skill_template(name: str, description: str, triggers: List[str], steps: str) -> str:
    """安装一个 skill 模板到用户目录"""
    _ensure_user_dir()
    target = SKILL_USER_DIR / f"{name}.md"
    if target.exists():
        return f"skill '{name}' 已存在"

    triggers_yaml = "\n".join(f"  - {t}" for t in triggers)
    content = f"""---
name: {name}
description: {description}
triggers:
{triggers_yaml}
steps: |
{chr(10).join("  " + s for s in steps.split(chr(10)))}
---

# {name}

{description}

## 步骤

{steps}

## 使用

```
/skill {name} <参数>
```

或自然语言触发(包含触发词)。
"""
    target.write_text(content, encoding="utf-8")
    return f"已安装 skill '{name}' 到 {target}"