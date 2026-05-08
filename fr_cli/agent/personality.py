"""
Personality 系统 - 参考 Hermes Agent 实现
支持多种 AI 个性切换
"""

import os
import json
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class Personality:
    """AI 个性"""
    name: str
    description: str
    identity: str
    system_prompt: str
    examples: list = None

    def __post_init__(self):
        if self.examples is None:
            self.examples = []

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "identity": self.identity,
            "system_prompt": self.system_prompt,
            "examples": self.examples
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Personality':
        return cls(**data)


class PersonalityManager:
    """个性管理器"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.expanduser("~/.fr_cli")
        self.config_dir = config_dir
        self.personalities: Dict[str, Personality] = {}
        self.current_personality: Optional[Personality] = None
        self._load_personalities()

    def _get_personalities_file(self) -> str:
        return os.path.join(self.config_dir, "personalities.json")

    def _load_personalities(self):
        """加载内置和用户个性"""
        self._register_builtin_personalities()

        config_file = self._get_personalities_file()
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for name, cfg in data.items():
                        self.personalities[name] = Personality.from_dict(cfg)
            except Exception:
                pass

        if not self.current_personality and self.personalities:
            self.current_personality = list(self.personalities.values())[0]

    def _register_builtin_personalities(self):
        """注册内置个性"""
        self.personalities = {
            "default": Personality(
                name="default",
                description="默认助手",
                identity="你是一个有帮助的 AI 助手。",
                system_prompt="你是一个有帮助的 AI 助手，擅长回答各种问题。"
            ),
            "coder": Personality(
                name="coder",
                description="编程专家",
                identity="你是一个专业的程序员。",
                system_prompt="""你是一个专业的程序员，擅长:
- Python, JavaScript, TypeScript, Go, Rust 等语言
- 代码审查和优化
- 调试和错误修复
- 设计模式和架构建议
- 编写测试和文档""",
                examples=["帮我写一个排序算法", "这段代码有什么问题?"]
            ),
            "reviewer": Personality(
                name="reviewer",
                description="代码审查员",
                identity="你是一个严格的代码审查员。",
                system_prompt="""你是一个严格的代码审查员，关注:
- 代码质量和可读性
- 性能和效率
- 安全漏洞
- 最佳实践
- 潜在的 bug

给出具体、可操作的改进建议。""",
                examples=["审查这段代码", "有什么安全问题?"]
            ),
            "teacher": Personality(
                name="teacher",
                description="编程教师",
                identity="你是一个耐心的编程教师。",
                system_prompt="""你是一个耐心的编程教师，特点:
- 解释清晰易懂
- 提供例子和类比
- 循序渐进
- 鼓励学习者
- 耐心回答问题""",
                examples=["解释什么是闭包", "面向对象是什么?"]
            ),
            "expert": Personality(
                name="expert",
                description="领域专家",
                identity="你是一个各个领域的专家。",
                system_prompt="""你是一个广博的领域专家，可以提供:
- 深入的技术分析
- 行业洞察
- 战略建议
- 最佳实践
- 前沿趋势""",
                examples=["分析这个架构的优缺点", "给我一些战略建议"]
            ),
            "creative": Personality(
                name="creative",
                description="创意助手",
                identity="你是一个富有创意的助手。",
                system_prompt="""你是一个富有创意的助手，擅长:
- 头脑风暴
- 生成创意点子
- 写作和内容创作
- 解决棘手问题
- 提供新颖的解决方案""",
                examples=["给我一些创意点子", "怎么让这个产品更有趣?"]
            )
        }

    def _save_personalities(self):
        """保存用户个性"""
        config_file = self._get_personalities_file()
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        data = {
            name: p.to_dict()
            for name, p in self.personalities.items()
            if name not in ["default", "coder", "reviewer", "teacher", "expert", "creative"]
        }
        if data:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def set_personality(self, name: str) -> bool:
        """设置当前个性"""
        if name in self.personalities:
            self.current_personality = self.personalities[name]
            return True
        return False

    def get_current(self) -> Optional[Personality]:
        """获取当前个性"""
        return self.current_personality

    def add_personality(self, personality: Personality):
        """添加用户个性"""
        self.personalities[personality.name] = personality
        self._save_personalities()

    def remove_personality(self, name: str) -> bool:
        """删除用户个性"""
        if name in ["default", "coder", "reviewer", "teacher", "expert", "creative"]:
            return False
        if name in self.personalities:
            del self.personalities[name]
            if self.current_personality and self.current_personality.name == name:
                self.current_personality = self.personalities.get("default")
            self._save_personalities()
            return True
        return False

    def list_personalities(self) -> list:
        """列出所有个性"""
        return [
            {
                "name": p.name,
                "description": p.description,
                "current": p == self.current_personality
            }
            for p in self.personalities.values()
        ]

    def build_system_prompt(self) -> str:
        """构建当前个性的系统提示"""
        if not self.current_personality:
            return ""

        p = self.current_personality
        parts = [
            f"# 身份: {p.identity}",
            f"\n{p.system_prompt}"
        ]

        if p.examples:
            parts.append("\n## 示例对话:")
            for ex in p.examples:
                parts.append(f"- {ex}")

        return "\n".join(parts)


# 全局实例
_personality_manager = None

def get_personality_manager() -> PersonalityManager:
    global _personality_manager
    if _personality_manager is None:
        _personality_manager = PersonalityManager()
    return _personality_manager


def set_personality(name: str) -> bool:
    """设置当前个性"""
    return get_personality_manager().set_personality(name)


def get_current_personality() -> Optional[Personality]:
    """获取当前个性"""
    return get_personality_manager().get_current()


def list_personalities() -> list:
    """列出所有个性"""
    return get_personality_manager().list_personalities()