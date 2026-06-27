"""
MasterAgent System Prompt 组装 Mixin

从 master.py 抽离出来，负责：
  - 工具描述动态生成（注册表 + MCP + Agent 列表）
  - System Prompt 完整组装（人设 + 技能 + 工具 + 进化追加 + 自治模式）
  - 插件/Agent 自动产物检测（辅助 handle 后处理）

通过 mixin 模式挂载到 MasterAgent 类，调用方代码（master._build_system_prompt()）保持不变。
"""
from fr_cli.agent.master_storage import (
    _DEFAULT_PERSONA,
    _DEFAULT_SKILLS,
)


class MasterAgentPromptMixin:
    """System Prompt 组装 mixin。

    需要 MasterAgent 提供：
      - self.state（含 .lang / .security / .client / .model_name / .messages / .context_summary
                  / .auto_session_path / .session_id / .save_cfg() / .sn / .cfg）
      - self.persona / self.skills / self.evolution / self.session
    """

    # ---------- 工具描述生成 ----------

    def _build_tools_desc(self):
        """从注册表动态生成工具描述文本，同时包含可用Agent列表"""
        from fr_cli.command.registry import get_registry
        from fr_cli.agent.client import discover_all_agents
        reg = get_registry()
        lines = []
        for t in reg.get_tools():
            params_str = ", ".join(f"{k}:{v.__name__ if hasattr(v, '__name__') else str(v)}"
                                    for k, v in t.get("params", {}).items())
            lines.append(f"- {t['name']}: {t['description']}  参数: {params_str or '无'}")

        # 追加 MCP 外部工具
        mcp_manager = getattr(self.state, "mcp", None)
        if mcp_manager:
            try:
                mcp_tools = mcp_manager.list_all_tools()
                if mcp_tools:
                    lines.append("\n=== MCP 外部工具 ===")
                    for t in mcp_tools:
                        lines.append(f"- {t['name']}: {t['description']}  (服务器: {t['server']})")
                    lines.append("\n调用方式: mcp_call({\"server\": \"服务器名\", \"tool\": \"工具名\", \"arguments\": {...}})")
            except Exception:
                pass

        # 追加可用 Agent 列表（本地 + 远程）
        agents = discover_all_agents()
        if agents:
            lines.append("\n=== 可协作的独立Agent ===")
            for a in agents:
                lines.append(f"- [{a['type']}] {a['name']}: {a['description']}")
            lines.append("\n调用方式: agent_call({\"name\": \"Agent名\", \"user_input\": \"任务描述\"})")
        return "\n".join(lines)

    # ---------- System Prompt 组装 ----------

    def _build_system_prompt(self, lang):
        """组装完整的 system prompt：人设 + 技能 + 工具 + 进化追加"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH, MASTER_SYSTEM_PROMPT_EN
        base_prompt = MASTER_SYSTEM_PROMPT_ZH if lang == "zh" else MASTER_SYSTEM_PROMPT_EN

        parts = [base_prompt.format(tools_desc=self._build_tools_desc())]

        # 自定义人设（去重：如果 persona.md 内容与默认不同才追加）
        custom_persona = self.persona.strip()
        if custom_persona and custom_persona != _DEFAULT_PERSONA.strip():
            parts.append(f"\n[自定义人设]\n{custom_persona}")

        # 技能装备
        skills_text = self.skills.strip()
        if skills_text and skills_text != _DEFAULT_SKILLS.strip():
            parts.append(f"\n[技能装备]\n{skills_text}")

        # 进化追加
        if self.evolution.get("prompt_addon"):
            parts.append(f"\n[进化补充提示]\n{self.evolution['prompt_addon']}")

        # 结构化失败提示
        failure_hints = self.evolution.get("failure_hints", [])
        if failure_hints:
            hint_lines = [f"- {h.get('tool')} ({h.get('error_type')}): {h.get('hint', '')}" for h in failure_hints[-5:]]
            parts.append("\n[高频失败与恢复提示]\n" + "\n".join(hint_lines))

        # 自治模式提示
        try:
            mode = getattr(self.state.security, "autonomous_mode", "manual")
            if mode == "sandbox_auto":
                if lang == "zh":
                    parts.append("\n[自治模式：沙盒内文件读写与网络搜索会自动执行；系统命令、安装包、发送邮件、MCP 等仍会询问或拒绝。]")
                else:
                    parts.append("\n[Autonomous mode: sandbox read/write/web fetch auto-execute; system commands, package install, email, MCP will still ask or be denied.]")
            elif mode == "full_auto":
                if lang == "zh":
                    parts.append("\n[自治模式：完全自动。所有工具调用都会自动执行，请谨慎决策。]")
                else:
                    parts.append("\n[Autonomous mode: full auto. All tool calls will execute automatically; decide carefully.]")
        except Exception:
            pass

        # 会话上下文延续
        if self.session.get("context_notes"):
            parts.append(f"\n[会话上下文]\n{self.session['context_notes']}")

        # 项目记忆(.frcli.md / AGENTS.md / CLAUDE.md 自动加载)
        try:
            from fr_cli.agent.project_memory import build_project_memory_section
            from pathlib import Path
            cwd = Path(getattr(self.state, "vfs", None) and self.state.vfs.cwd or ".").resolve()
            memory_section = build_project_memory_section(cwd)
            if memory_section:
                parts.append(f"\n{memory_section}")
        except Exception:
            pass

        return "\n".join(parts)

    # ---------- 插件 / Agent 自动检测 ----------

    def _detect_artifacts(self, txt, lang, background=False):
        """检测 AI 回复中的插件/Agent 代码结构，提示用户保存"""
        if not txt:
            return
        from fr_cli.agent.artifact_detector import detect_plugin_artifact, detect_agent_artifact
        detect_plugin_artifact(txt, lang, self.state, interactive=not background)
        detect_agent_artifact(txt, lang, self.state, interactive=not background)
