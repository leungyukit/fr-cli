"""
自动记忆总结和知识库更新系统
- 根据用户问题和回复自动总结
- 更新知识库
- 形成持久化知识
"""

import os
import json
import time
from typing import List, Dict, Any, Optional
from collections import defaultdict


class ConversationSummary:
    """对话总结器"""

    @staticmethod
    def summarize(user_input: str, ai_response: str, context: Dict = None) -> str:
        """生成对话摘要"""
        # 提取关键信息
        key_points = []

        # 话题识别
        topics = ConversationSummary._extract_topics(user_input)
        key_points.extend(topics)

        # 意图识别
        intents = ConversationSummary._extract_intents(user_input)
        key_points.extend(intents)

        # 知识点提取
        knowledge = ConversationSummary._extract_knowledge(ai_response)
        key_points.extend(knowledge)

        return "\n".join(f"• {k}" for k in key_points[:5])

    @staticmethod
    def _extract_topics(text: str) -> List[str]:
        """提取话题"""
        topics = []
        keywords_map = {
            "python": ["Python", "代码", "编程"],
            "git": ["Git", "版本控制", "commit"],
            "api": ["API", "接口", "请求"],
            "数据库": ["数据库", "SQL", "查询"],
            "web": ["Web", "前端", "后端", "HTTP"],
            "docker": ["Docker", "容器", "镜像"],
            "测试": ["测试", "test", "pytest"],
            "部署": ["部署", "deploy", "服务器"],
        }

        text_lower = text.lower()
        for topic, keywords in keywords_map.items():
            if any(k.lower() in text_lower for k in keywords):
                topics.append(f"话题: {topic}")

        return topics[:5]

    @staticmethod
    def _extract_intents(text: str) -> List[str]:
        """提取意图"""
        intents = []
        text_lower = text.lower()

        if "如何" in text or "how to" in text_lower:
            intents.append("操作指南")
        if "为什么" in text or "原因" in text:
            intents.append("问题解答")
        if "比较" in text or "区别" in text:
            intents.append("对比分析")
        if "实现" in text or "create" in text_lower:
            intents.append("实现方案")

        return intents[:3]

    @staticmethod
    def _extract_knowledge(text: str) -> List[str]:
        """提取知识点"""
        knowledge = []
        # 提取代码片段
        if "```" in text:
            knowledge.append("代码示例")
        # 提取命令
        if any(cmd in text for cmd in ["pip", "git", "docker", "curl"]):
            knowledge.append("命令操作")
        # 提取配置
        if "=" in text or ":" in text:
            knowledge.append("配置参数")
        return knowledge[:3]


class KnowledgeBase:
    """知识库管理器"""

    def __init__(self, kb_file: str = None):
        if kb_file is None:
            kb_file = os.path.expanduser("~/.fr_cli_knowledge.json")
        self.kb_file = kb_file
        self.knowledge: Dict[str, List[Dict]] = defaultdict(list)
        self._load()

    def _load(self):
        """加载知识库"""
        if os.path.exists(self.kb_file):
            try:
                with open(self.kb_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.knowledge = defaultdict(list, data)
            except Exception:
                pass

    def _save(self):
        """保存知识库"""
        try:
            os.makedirs(os.path.dirname(self.kb_file), exist_ok=True)
            with open(self.kb_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self.knowledge), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, topic: str, entry: str):
        """添加知识条目"""
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        self.knowledge[topic].append({
            "content": entry,
            "timestamp": timestamp,
            "access_count": 0
        })
        self._save()

    def search(self, query: str) -> List[Dict]:
        """搜索知识"""
        results = []
        query_lower = query.lower()

        for topic, entries in self.knowledge.items():
            for entry in entries:
                if query_lower in topic.lower() or query_lower in entry.get("content", "").lower():
                    entry["access_count"] = entry.get("access_count", 0) + 1
                    results.append({
                        "topic": topic,
                        **entry
                    })

        self._save()
        return sorted(results, key=lambda x: x.get("access_count", 0), reverse=True)[:10]

    def update_from_conversation(self, user_input: str, ai_response: str):
        """从对话更新知识库"""
        summary = ConversationSummary.summarize(user_input, ai_response)
        if summary:
            # 提取主话题
            topic = self._extract_main_topic(user_input)
            self.add(topic, f"Q: {user_input}\nA: {ai_response[:200]}...")

    def _extract_main_topic(self, text: str) -> str:
        """提取主话题"""
        # 简单的话题提取逻辑
        if "python" in text.lower():
            return "Python编程"
        if "git" in text.lower():
            return "Git版本控制"
        if "api" in text.lower() or "接口" in text:
            return "API开发"
        if "docker" in text.lower():
            return "Docker容器"
        if "部署" in text or "deploy" in text.lower():
            return "部署运维"
        if "测试" in text or "test" in text.lower():
            return "测试调试"
        return "通用知识"

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "topics": len(self.knowledge),
            "entries": sum(len(v) for v in self.knowledge.values()),
            "knowledge_base_size_kb": os.path.getsize(self.kb_file) / 1024 if os.path.exists(self.kb_file) else 0
        }


# 全局知识库实例
_knowledge_base = None

def get_knowledge_base() -> KnowledgeBase:
    """获取知识库实例"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base
