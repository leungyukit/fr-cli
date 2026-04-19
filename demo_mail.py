#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件功能演示 — 在控制台展示收件箱列表和邮件详情
"""
import sys, os
from unittest.mock import MagicMock

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.weapon.fs import VFS
from fr_cli.command.executor import CommandExecutor
from fr_cli.ui.ui import CYAN, GREEN, YELLOW, RESET, BOLD

WORKSPACE = os.path.join(project_root, "workspaces")
os.makedirs(WORKSPACE, exist_ok=True)

# 初始化执行器，mail_c 用真实逻辑但数据 mock
mail_c = MagicMock()
mail_c.inbox.return_value = (
    [
        {"id": "1001", "sub": "【系统通知】您的 API Key 已续期", "from": "noreply@zhipuai.cn"},
        {"id": "1002", "sub": "项目周报 - 2026年第16周", "from": "pm@company.com"},
        {"id": "1003", "sub": "Re: 关于 fr-cli 架构调整的讨论", "from": "dev@team.com"},
        {"id": "1004", "sub": "阿里云盘存储空间即将到期提醒", "from": "aliyun@notice.com"},
        {"id": "1005", "sub": "GitHub: New issue in fr-cli", "from": "github@noreply.com"},
    ],
    None
)

mail_c.send.return_value = (True, None)
mail_c.read.side_effect = lambda mid, lang: (
    {
        "sub": "Re: 关于 fr-cli 架构调整的讨论",
        "from": "dev@team.com",
        "date": "Thu, 17 Apr 2026 14:32:08 +0800",
        "body": "架构调整方案已确认，建议按以下步骤执行：\n\n1. 新增 invoke_tool 方法\n2. 修改 process_ai_commands 解析逻辑\n3. 更新 WEAPON.MD 和 system prompt\n4. 补充集成测试\n\n如有问题请随时沟通。"
    },
    None
)

vfs = VFS([WORKSPACE])
cfg = {"session_name": "", "model": "glm-4-flash", "lang": "zh", "key": "demo"}

executor = CommandExecutor(
    vfs=vfs, mail_c=mail_c, web_c=MagicMock(), disk_c=MagicMock(),
    plugins={}, lang="zh", security=None, cfg=cfg,
    client=MagicMock(), model_name="glm-4-flash"
)

print("\n" + "█"*60)
print("█" + "  📧 凡人打字机 — 邮件功能演示".center(54) + "█")
print("█"*60)

# ========== 场景1: AI 调用查看收件箱 ==========
print(f"\n{BOLD}{CYAN}>>> 场景 1: 用户说 '查看我的邮件'{RESET}\n")
print("  🤖 AI 回复:")
print("  " + "-"*50)
ai_reply = '''好的，我来查看您的收件箱。

【调用：mail_inbox({})】

以上是最近 5 封邮件。'''
for line in ai_reply.split('\n'):
    print(f"     {line}")
print("  " + "-"*50)

clean, results = executor.process_ai_commands(ai_reply)

print(f"\n  ⚡ 执行结果:")
for r in results:
    print(f"     {r}")

# 手动展示邮件列表（模拟控制台显示效果）
print(f"\n  {BOLD}{GREEN}📬 收件箱邮件列表:{RESET}")
mails, _ = mail_c.inbox("zh")
for i, m in enumerate(mails, 1):
    print(f"     {YELLOW}[{i}]{RESET} ID:{m['id']} | {m['sub'][:40]} | 来自: {m['from']}")

# ========== 场景2: AI 调用读取指定邮件 ==========
print(f"\n{BOLD}{CYAN}>>> 场景 2: 用户说 '读一下第3封邮件'{RESET}\n")
print("  🤖 AI 回复:")
print("  " + "-"*50)
ai_reply2 = '''为您读取第3封邮件。

【调用：mail_read({"id": "1003"})】

邮件内容如上。'''
for line in ai_reply2.split('\n'):
    print(f"     {line}")
print("  " + "-"*50)

clean2, results2 = executor.process_ai_commands(ai_reply2)

print(f"\n  ⚡ 执行结果:")
for r in results2:
    print(f"     {r}")

# 手动展示邮件详情
mail_data, _ = mail_c.read("1003", "zh")
print(f"\n  {BOLD}{GREEN}📧 邮件详情:{RESET}")
print(f"     主题: {mail_data['sub']}")
print(f"     发件人: {mail_data['from']}")
print(f"     时间: {mail_data['date']}")
print(f"     {CYAN}{'─'*40}{RESET}")
for line in mail_data['body'].split('\n'):
    print(f"     {line}")

# ========== 场景3: AI 调用发送邮件 ==========
print(f"\n{BOLD}{CYAN}>>> 场景 3: 用户说 '回复这封邮件说收到了'{RESET}\n")
print("  🤖 AI 回复:")
print("  " + "-"*50)
ai_reply3 = '''为您回复邮件。

【调用：mail_send({"to": "dev@team.com", "subject": "Re: 关于 fr-cli 架构调整的讨论", "body": "已收到，我会按照步骤执行架构调整。感谢指导！"})】

回复已发送。'''
for line in ai_reply3.split('\n'):
    print(f"     {line}")
print("  " + "-"*50)

clean3, results3 = executor.process_ai_commands(ai_reply3)

print(f"\n  ⚡ 执行结果:")
for r in results3:
    print(f"     {r}")

print(f"\n{BOLD}{GREEN}✅ 邮件功能演示完成{RESET}\n")
