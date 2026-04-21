#!/usr/bin/env python3
"""
真实 API 演示脚本：验证大模型自主判定并调用工具的完整流程

用法：
    1. 确保 ~/.zhipu_cli_config.json 中已配置有效的 API Key
    2. cd /Users/liangyj/workspace/glm-cli
    3. python tests/run_live_demo.py

本脚本会自动运行以下场景的端到端测试：
    - 场景1：用户要求查看目录 → AI 应自动调用 /ls
    - 场景2：用户要求创建文件 → AI 应自动调用 /write
    - 场景3：用户要求搜索 → AI 应自动调用 /web
    - 场景4：用户简单问候 → AI 应直接回答，不调用工具
"""
import sys
import os
import tempfile

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.conf.config import load_config
from fr_cli.lang.i18n import T
from fr_cli.weapon.fs import VFS
from fr_cli.weapon.loader import load_weapon_md, get_available_tools
from fr_cli.command.security import SecurityManager
from fr_cli.command.executor import CommandExecutor
from fr_cli.core.stream import stream_cnt
from zhipuai import ZhipuAI


def run_demo():
    cfg = load_config()
    if not cfg.get("key"):
        print("❌ 请先配置 API Key：运行 python fr_cli/main.py 并按提示输入")
        return 1

    lang = cfg.get("lang", "zh")
    model_name = cfg.get("model", "glm-4-flash")
    client = ZhipuAI(api_key=cfg["key"])

    # 创建临时 VFS 沙盒
    temp_dir = os.path.realpath(tempfile.mkdtemp())
    from types import SimpleNamespace
    vfs = VFS([temp_dir])
    security = SecurityManager(lang, cfg)
    mock_state = SimpleNamespace(
        vfs=vfs, mail_c=None, web_c=None, disk_c=None,
        plugins={}, lang=lang, security=security, cfg=cfg,
        client=client, model_name=model_name
    )
    executor = CommandExecutor(mock_state)
    weapon_tools, weapon_triggers = load_weapon_md()

    print(f"🧪 测试环境就绪")
    print(f"   模型: {model_name}")
    print(f"   语言: {lang}")
    print(f"   沙盒: {temp_dir}")
    print()

    scenarios = [
        ("场景1：查看目录", "帮我看看当前目录有什么文件"),
        ("场景2：创建文件", '在当前目录创建一个名为 demo.txt 的文件，内容是 "hello world"'),
        ("场景3：简单问候", "你好，请介绍一下你自己"),
    ]

    for title, user_input in scenarios:
        print(f"\n{'='*50}")
        print(f"📢 {title}")
        print(f"🧑 用户: {user_input}")
        print(f"{'='*50}")

        # 构造 messages
        sp = T("sys_prompt", lang)
        messages = [{"role": "system", "content": sp}]

        # 注入工具列表（MasterAgent 模式下始终注入全部可用工具）
        tools = get_available_tools(weapon_tools, {})
        tools_info = "\n\n当前可用的工具列表：\n"
        for i, tool in enumerate(tools, 1):
            tools_info += f"{i}. {tool['name']}: {tool['description']}\n   可用命令: {', '.join(tool['commands'])}\n"
        messages[0]["content"] = sp + tools_info
        print(f"🔧 [系统] 已注入工具信息（MasterAgent 模式始终注入全部工具）")

        # 追加用户输入
        prompt = user_input
        if vfs.cwd:
            prompt += T("ctx_dir", lang, vfs.cwd)
        messages.append({"role": "user", "content": prompt})

        # 调用大模型
        print(f"🤖 [AI 思考中...]")
        try:
            txt, usage, response_time = stream_cnt(client, model_name, messages, lang)
        except Exception as e:
            print(f"❌ API 调用失败: {e}")
            continue

        messages.append({"role": "assistant", "content": txt})

        # 自动执行命令
        clean_txt, cmd_results = executor.process_ai_commands(txt, messages)

        if cmd_results:
            print(f"\n🤖 自动执行命令:")
            for r in cmd_results:
                print(f"   {r}")

            # 将结果回传给 AI
            messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
            messages.append({
                "role": "system",
                "content": f"命令执行结果:\n" + "\n".join(cmd_results)
            })

            print(f"\n🤖 [AI 基于执行结果生成最终回复...]")
            final_txt, _, _ = stream_cnt(client, model_name, messages, lang, custom_prefix="")
            messages.append({"role": "assistant", "content": final_txt})
        else:
            print(f"\n📢 [AI 直接回答，未调用工具]")

        print(f"\n✅ {title} 完成")

    # 清理
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"\n🧹 沙盒已清理")
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
