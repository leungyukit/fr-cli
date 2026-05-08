"""
Skills 系统 - 参考 Hermes Agent 实现
技能是 AI 自我学习的核心机制
"""

import os
import json
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class Skill:
    """技能"""
    name: str
    description: str
    content: str
    author: str = "system"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    usage_count: int = 0
    success_count: int = 0
    tags: List[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "tags": self.tags,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Skill':
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            content=data["content"],
            author=data.get("author", "system"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            usage_count=data.get("usage_count", 0),
            success_count=data.get("success_count", 0),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True)
        )


class SkillManager:
    """技能管理器"""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            skills_dir = os.path.expanduser("~/.fr_cli/skills")
        self.skills_dir = skills_dir
        self.skills: Dict[str, Skill] = {}
        self._load_skills()
        self._ensure_dir()

    def _ensure_dir(self):
        """确保目录存在"""
        os.makedirs(self.skills_dir, exist_ok=True)

    def _load_skills(self):
        """加载所有技能"""
        if not os.path.exists(self.skills_dir):
            return

        for filename in os.listdir(self.skills_dir):
            if filename.endswith('.json'):
                skill_path = os.path.join(self.skills_dir, filename)
                try:
                    with open(skill_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        skill = Skill.from_dict(data)
                        self.skills[skill.name] = skill
                except Exception:
                    pass

    def _save_skill(self, skill: Skill):
        """保存技能"""
        self._ensure_dir()
        filename = f"{skill.name}.json".replace("/", "_")
        filepath = os.path.join(self.skills_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(skill.to_dict(), f, ensure_ascii=False, indent=2)

    def create_skill(self, name: str, description: str, content: str,
                     author: str = "user", tags: List[str] = None) -> Skill:
        """创建技能"""
        skill = Skill(
            name=name,
            description=description,
            content=content,
            author=author,
            tags=tags or []
        )
        self.skills[name] = skill
        self._save_skill(skill)
        return skill

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)

    def update_skill(self, name: str, **kwargs):
        """更新技能"""
        if name in self.skills:
            skill = self.skills[name]
            for key, value in kwargs.items():
                if hasattr(skill, key):
                    setattr(skill, key, value)
            skill.updated_at = time.time()
            self._save_skill(skill)
            return skill
        return None

    def delete_skill(self, name: str) -> bool:
        """删除技能"""
        if name in self.skills:
            del self.skills[name]
            filename = f"{name}.json".replace("/", "_")
            filepath = os.path.join(self.skills_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        return False

    def list_skills(self, enabled_only: bool = True) -> List[Skill]:
        """列出技能"""
        skills = list(self.skills.values())
        if enabled_only:
            skills = [s for s in skills if s.enabled]
        return skills

    def search_skills(self, query: str) -> List[Skill]:
        """搜索技能"""
        query_lower = query.lower()
        results = []
        for skill in self.skills.values():
            if (query_lower in skill.name.lower() or
                query_lower in skill.description.lower() or
                any(query_lower in tag.lower() for tag in skill.tags)):
                results.append(skill)
        return results

    def record_usage(self, name: str, success: bool = True):
        """记录技能使用"""
        if name in self.skills:
            skill = self.skills[name]
            skill.usage_count += 1
            if success:
                skill.success_count += 1
            self._save_skill(skill)

    def build_system_prompt(self) -> str:
        """构建技能系统提示"""
        skills = self.list_skills()
        if not skills:
            return ""

        lines = ["\n\n# 可用技能"]
        for skill in skills:
            lines.append(f"\n## {skill.name}")
            lines.append(f"描述: {skill.description}")
            lines.append(f"内容:\n{skill.content}")

        return "\n".join(lines)

    def learn_from_task(self, task: str, result: str, context: str = ""):
        """从任务中学习并创建技能"""
        skill = Skill(
            name=f"skill_{int(time.time())}",
            description=f"从任务 '{task[:50]}...' 学习",
            content=f"任务: {task}\n\n结果: {result}\n\n上下文: {context}",
            author="auto"
        )
        self.skills[skill.name] = skill
        self._save_skill(skill)
        return skill

    def get_stats(self) -> Dict:
        """获取统计"""
        skills = list(self.skills.values())
        return {
            "total": len(skills),
            "enabled": sum(1 for s in skills if s.enabled),
            "total_usage": sum(s.usage_count for s in skills),
            "success_rate": (
                sum(s.success_count for s in skills) /
                max(1, sum(s.usage_count for s in skills))
            )
        }


# 全局实例
_skill_manager = None

def get_skill_manager() -> SkillManager:
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


def create_skill(name: str, description: str, content: str) -> Skill:
    """创建技能快捷方法"""
    return get_skill_manager().create_skill(name, description, content)


def list_skills() -> List[Skill]:
    """列出所有技能"""
    return get_skill_manager().list_skills()


def search_skills(query: str) -> List[Skill]:
    """搜索技能"""
    return get_skill_manager().search_skills(query)