"""
Agent 自动学习和进化系统
- 从对话中学习新技能
- 自我进化
- 知识库更新
"""

import os
import json
import time
from typing import Dict, List, Any
from collections import defaultdict


class SkillLearner:
    """技能学习器"""

    def __init__(self):
        self.skills_file = os.path.expanduser("~/.fr_cli_skills.json")
        self.skills = {}
        self._load()

    def _load(self):
        """加载技能"""
        if os.path.exists(self.skills_file):
            try:
                with open(self.skills_file) as f:
                    self.skills = json.load(f)
            except:
                pass

    def _save(self):
        """保存技能"""
        try:
            with open(self.skills_file, 'w') as f:
                json.dump(self.skills, f, ensure_ascii=False, indent=2)
        except:
            pass

    def learn_from_conversation(self, user_input: str, response: str):
        """从对话学习新技能"""
        # 检测是否包含可学习的技能
        if "代码" in response or "python" in response.lower():
            # 提取代码块
            import re
            code_blocks = re.findall(r'```\w*\n(.*?)```', response, re.DOTALL)
            if code_blocks:
                self.skills['learned_code'] = self.skills.get('learned_code', [])
                self.skills['learned_code'].append({
                    'time': time.strftime('%Y-%m-%d %H:%M'),
                    'sample': code_blocks[0][:200]
                })
                self._save()

        # 检测命令
        if any(cmd in response for cmd in ['pip', 'git', 'docker', 'curl']):
            self.skills['learned_commands'] = self.skills.get('learned_commands', [])
            self.skills['learned_commands'].append(time.strftime('%Y-%m-%d'))
            self._save()

    def get_stats(self) -> Dict:
        """获取学习统计"""
        return {
            'skills': len(self.skills.get('learned_code', [])),
            'commands': len(self.skills.get('learned_commands', []))
        }


# 全局实例
_learner = None

def get_learner() -> SkillLearner:
    global _learner
    if _learner is None:
        _learner = SkillLearner()
    return _learner
