#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
凡人打字机 — 逐步演示脚本
每执行一个场景后，展示工作空间的文件变化。
"""
import sys, os, time
from unittest.mock import MagicMock

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.weapon.fs import VFS
from fr_cli.command.executor import CommandExecutor

WORKSPACE = os.path.join(project_root, "workspaces")
os.makedirs(WORKSPACE, exist_ok=True)

def init_executor():
    vfs = VFS([WORKSPACE])
    mail_c = MagicMock()
    web_c = MagicMock()
    web_c.search.return_value = ([{"title":"Python官网","url":"https://python.org","snippet":"Python是一种广泛使用的编程语言。"}], None)
    web_c.fetch.return_value = ("网页正文示例内容。\n这是第二行。", None)
    disk_c = MagicMock()
    disk_c.ls.return_value = (["云端文件1.txt","云端文件2.pdf"], None)
    disk_c.up.return_value = (True, "✅ 上传成功")
    mail_c.inbox.return_value = ([{"id":"1","sub":"欢迎邮件","from":"admin@example.com"}], None)
    mail_c.send.return_value = (True, None)
    cfg = {"session_name":"","model":"glm-4-flash","lang":"zh","key":"demo"}
    return CommandExecutor(vfs=vfs, mail_c=mail_c, web_c=web_c, disk_c=disk_c,
        plugins={}, lang="zh", security=None, cfg=cfg,
        client=MagicMock(), model_name="glm-4-flash")

executor = init_executor()

def divider(title):
    print("\n" + "="*70)
    print(f"  >>> {title}")
    print("="*70)

def show_workspace():
    files = sorted(os.listdir(WORKSPACE))
    print(f"\n  📂 工作空间当前文件 ({len(files)} 个):")
    for f in files:
        size = os.path.getsize(os.path.join(WORKSPACE, f))
        print(f"     - {f} ({size} bytes)")

def step(name, ai_response, msgs=None):
    divider(name)
    print(f"\n  🤖 AI 回复:\n{'-'*50}")
    for line in ai_response.split('\n'):
        print(f"     {line}")
    print(f"{'-'*50}")

    clean, results = executor.process_ai_commands(ai_response, msgs)

    print(f"\n  ⚡ 工具执行结果:")
    for r in results:
        print(f"     {r}")

    print(f"\n  📝 清理后展示给用户的内容:\n{'-'*50}")
    for line in clean.split('\n'):
        if line.strip():
            print(f"     {line}")
    print(f"{'-'*50}")

    show_workspace()

# ========== 开始演示 ==========
print("\n" + "█"*70)
print("█" + " "*68 + "█")
print("█" + "  凡人打字机 (fr-cli) — 结构化工具调用逐步演示".center(62) + "█")
print("█" + " "*68 + "█")
print("█"*70)
show_workspace()

# 步骤1: 写入文件
step("步骤 1: AI 自动写入 Markdown 文件",
'''好的，我来为您保存 PMO 定义。

【调用：write_file({"path": "PMO_Definition.md", "content": "# PMO的定义\n\nPMO是项目管理办公室（Project Management Office）的缩写，它是一个组织内部专门负责项目管理的部门或团队。\n\n## 主要职责\n- 规划、指导和管理组织的项目管理实践\n- 制定和实施项目管理政策和程序\n- 提供项目管理培训和认证\n- 监督和评估项目绩效\n- 支持项目团队并促进跨部门协作\n\nPMO在组织中的角色非常重要，它有助于提高项目管理水平，确保项目成功，并最终实现组织的战略目标。"})】

已为您保存到 PMO_Definition.md。''')

# 步骤2: 读取文件
step("步骤 2: AI 读取刚保存的文件",
'''文件内容如下：

【调用：read_file({"path": "PMO_Definition.md"})】

如上所示。''')

# 步骤3: 列出文件
step("步骤 3: AI 列出当前目录",
'''当前目录文件如下：

【调用：list_files({})】

以上是当前目录的所有文件。''')

# 步骤4: 搜索网页
step("步骤 4: AI 联网搜索",
'''我来搜索一下 Python 最新版本信息。

【调用：search_web({"query": "Python 最新版本"})】

搜索完成，结果如上。''')

# 步骤5: 追加文件
step("步骤 5: AI 将搜索结果追加到文件",
'''我将搜索结果追加到 PMO_Definition.md 末尾。

【调用：append_file({"path": "PMO_Definition.md", "content": "\n\n---\n\n## 参考资料\n- Python 官网: https://python.org\n- 搜索时间: 2026-04-19"})】

已追加。''')

# 步骤6: 再次读取，验证追加
step("步骤 6: 验证追加后的完整内容",
'''更新后的完整内容：

【调用：read_file({"path": "PMO_Definition.md"})】

内容如上。''')

# 步骤7: 邮件
step("步骤 7: AI 查看邮件收件箱",
'''我来查看您的邮件。

【调用：mail_inbox({})】

以上是收件箱内容。''')

# 步骤8: 发送邮件
step("步骤 8: AI 发送邮件",
'''发送一封测试邮件。

【调用：mail_send({"to": "test@example.com", "subject": "PMO介绍", "body": "PMO是项目管理办公室的缩写，详见附件。"})】

邮件已发送。''')

# 步骤9: 云盘
step("步骤 9: AI 查看云盘文件",
'''查看云盘文件列表。

【调用：disk_ls({})】

云盘文件如上。''')

# 步骤10: 云盘上传
step("步骤 10: AI 上传文件到云盘",
'''将 PMO_Definition.md 上传到云盘备份。

【调用：disk_up({"local": "PMO_Definition.md", "remote": "/backup/PMO_Definition.md"})】

上传完成。''')

# 步骤11: 定时任务
step("步骤 11: AI 添加定时任务",
'''添加一个每小时列出文件的定时任务。

【调用：cron_add({"command": "/ls", "interval": 3600})】

定时任务已添加。''')

# 步骤12: 旧格式兼容
step("步骤 12: 旧格式兼容测试（file_operations/write）",
'''保存一个兼容测试文件。

file_operations
/write compat_test.md "旧格式兼容测试内容"

已保存。''')

# 步骤13: 删除文件
step("步骤 13: AI 删除测试文件",
'''删除兼容测试文件。

【调用：delete_file({"path": "compat_test.md"})】

已删除。''')

# 步骤14: 配置切换
step("步骤 14: AI 切换模型配置",
'''切换为更强的模型。

【调用：set_model({"name": "glm-4-plus"})】

模型已切换为 glm-4-plus。''')

# 最终汇总
divider("演示完成")
print("\n  ✅ 所有 14 个场景执行完毕")
print("  ✅ 工作空间中的文件真实存在，可查看")
print("  ✅ 文件内容完整保留换行和格式")
show_workspace()
print("")
