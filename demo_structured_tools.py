#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
凡人打字机 (fr-cli) — 结构化工具调用演示
在工作空间 workspaces/ 下真实执行各类工具调用，并生成测试报告。
"""
import sys
import os
import json
from datetime import datetime
from unittest.mock import MagicMock

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.weapon.fs import VFS
from fr_cli.command.executor import CommandExecutor

WORKSPACE = os.path.join(project_root, "workspaces")
os.makedirs(WORKSPACE, exist_ok=True)

REPORT_FILE = os.path.join(WORKSPACE, "structured_tools_demo_report.md")


def init_executor():
    """初始化执行器，使用 workspaces/ 作为工作目录"""
    vfs = VFS([WORKSPACE])
    # 预先创建一些测试文件
    with open(os.path.join(WORKSPACE, "hello.txt"), "w", encoding="utf-8") as f:
        f.write("Hello, 凡人打字机!\n这是一行测试文本。\n")

    # Mock 外部依赖（不需要真实 API key）
    mail_c = MagicMock()
    web_c = MagicMock()
    web_c.search.return_value = (
        [{"title": "Python 官网", "url": "https://python.org", "snippet": "Python 是一种广泛使用的编程语言。"}],
        None
    )
    web_c.fetch.return_value = ("网页正文示例内容。\n这是第二行。", None)

    disk_c = MagicMock()
    disk_c.ls.return_value = (["云端文件1.txt", "云端文件2.pdf"], None)
    disk_c.up.return_value = (True, "✅ 上传成功")
    disk_c.down.return_value = (True, "✅ 下载成功")

    mail_c.inbox.return_value = (
        [{"id": "1", "sub": "欢迎邮件", "from": "admin@example.com"}],
        None
    )
    mail_c.send.return_value = (True, None)

    cfg = {
        "session_name": "demo",
        "model": "glm-4-flash",
        "lang": "zh",
        "key": "demo-key"
    }
    client = MagicMock()

    return CommandExecutor(
        vfs=vfs, mail_c=mail_c, web_c=web_c, disk_c=disk_c,
        plugins={}, lang="zh", security=None, cfg=cfg,
        client=client, model_name="glm-4-flash"
    )


def run_scenario(executor, name, ai_response, msgs=None):
    """执行一个模拟 AI 场景，返回 (clean, results, success)"""
    print(f"\n{'='*60}")
    print(f"场景: {name}")
    print(f"{'='*60}")
    print(f"AI 原始回复:\n{ai_response}\n")

    clean, results = executor.process_ai_commands(ai_response, msgs)

    print(f"清理后回复:\n{clean}\n")
    print("执行结果:")
    for r in results:
        print(f"  {r}")

    success = all("❌" not in r for r in results) and len(results) > 0
    return clean, results, success


def main():
    executor = init_executor()
    report_lines = [
        "# 凡人打字机 — 结构化工具调用测试报告",
        f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n> 本报告由 `demo_structured_tools.py` 自动生成，",
        "> 在 `workspaces/` 目录下真实执行各类工具调用后汇总。",
        "\n---\n"
    ]

    scenarios = []

    # ========== 场景1: 文件写入（含换行） ==========
    ai = '''用户要求保存 PMO 定义。

【调用：write_file({"path": "PMO_Definition.md", "content": "# PMO的定义\n\nPMO是项目管理办公室（Project Management Office）的缩写。\n\n## 主要职责\n- 规划、指导和管理组织的项目管理实践\n- 制定和实施项目管理政策和程序\n- 提供项目管理培训和认证\n- 监督和评估项目绩效\n- 支持项目团队并促进跨部门协作\n\nPMO在组织中的角色非常重要，它有助于提高项目管理水平，确保项目成功，并最终实现组织的战略目标。"})】

已为您保存到 PMO_Definition.md。'''
    _, results, ok = run_scenario(executor, "文件写入（含多级标题、列表、换行）", ai)
    scenarios.append(("write_file", "文件写入", ok, results))

    # ========== 场景2: 文件读取 ==========
    ai = '''用户要求查看 hello.txt 内容。

【调用：read_file({"path": "hello.txt"})】

文件内容如上。'''
    _, results, ok = run_scenario(executor, "文件读取", ai)
    scenarios.append(("read_file", "文件读取", ok, results))

    # ========== 场景3: 列出文件 ==========
    ai = '''用户要求列出当前目录。

【调用：list_files({})】

以上是当前目录的文件列表。'''
    _, results, ok = run_scenario(executor, "列出文件", ai)
    scenarios.append(("list_files", "列出文件", ok, results))

    # ========== 场景4: 追加内容 ==========
    ai = '''用户要求在 hello.txt 末尾追加内容。

【调用：append_file({"path": "hello.txt", "content": "\n---\n追加内容：测试完成时间：2026-04-19"})】

已追加。'''
    _, results, ok = run_scenario(executor, "追加文件内容", ai)
    scenarios.append(("append_file", "追加文件", ok, results))

    # ========== 场景5: 搜索网页 ==========
    ai = '''用户要求搜索 Python 教程。

【调用：search_web({"query": "Python 最新教程"})】

搜索完成。'''
    _, results, ok = run_scenario(executor, "网络搜索", ai)
    scenarios.append(("search_web", "网络搜索", ok, results))

    # ========== 场景6: 抓取网页 ==========
    ai = '''用户要求抓取 example.com。

【调用：fetch_web({"url": "https://example.com"})】

抓取完成。'''
    _, results, ok = run_scenario(executor, "网页抓取", ai)
    scenarios.append(("fetch_web", "网页抓取", ok, results))

    # ========== 场景7: 邮件收件箱 ==========
    ai = '''用户要求查看邮件。

【调用：mail_inbox({})】

邮件列表如上。'''
    _, results, ok = run_scenario(executor, "查看邮件收件箱", ai)
    scenarios.append(("mail_inbox", "邮件收件箱", ok, results))

    # ========== 场景8: 发送邮件 ==========
    ai = '''用户要求发送邮件。

【调用：mail_send({"to": "test@example.com", "subject": "测试邮件", "body": "这是由凡人打字机自动发送的测试邮件。"})】

邮件已发送。'''
    _, results, ok = run_scenario(executor, "发送邮件", ai)
    scenarios.append(("mail_send", "发送邮件", ok, results))

    # ========== 场景9: 云盘列出 ==========
    ai = '''用户要求查看云盘文件。

【调用：disk_ls({})】

云盘文件如上。'''
    _, results, ok = run_scenario(executor, "云盘文件列表", ai)
    scenarios.append(("disk_ls", "云盘列表", ok, results))

    # ========== 场景10: 云盘上传 ==========
    ai = '''用户要求上传文件到云盘。

【调用：disk_up({"local": "hello.txt", "remote": "/backup/hello.txt"})】

上传完成。'''
    _, results, ok = run_scenario(executor, "云盘上传", ai)
    scenarios.append(("disk_up", "云盘上传", ok, results))

    # ========== 场景11: 定时任务添加 ==========
    ai = '''用户要求添加定时任务。

【调用：cron_add({"command": "/ls", "interval": 60})】

定时任务已添加。'''
    _, results, ok = run_scenario(executor, "添加定时任务", ai)
    scenarios.append(("cron_add", "定时任务", ok, results))

    # ========== 场景12: 会话保存 ==========
    msgs = [{"role": "user", "content": "测试消息"}, {"role": "assistant", "content": "测试回复"}]
    ai = '''用户要求保存当前会话。

【调用：save_session({"name": "demo_session"})】

会话已保存。'''
    _, results, ok = run_scenario(executor, "保存会话", ai, msgs)
    scenarios.append(("save_session", "会话保存", ok, results))

    # ========== 场景13: 列出会话 ==========
    ai = '''用户要求列出所有会话。

【调用：list_sessions({})】

会话列表如上。'''
    _, results, ok = run_scenario(executor, "列出会话", ai)
    scenarios.append(("list_sessions", "列出会话", ok, results))

    # ========== 场景14: 配置切换模型 ==========
    ai = '''用户要求切换模型。

【调用：set_model({"name": "glm-4-plus"})】

模型已切换。'''
    _, results, ok = run_scenario(executor, "切换模型配置", ai)
    scenarios.append(("set_model", "配置管理", ok, results))

    # ========== 场景15: 旧格式兼容 ==========
    ai = '''用户要求保存文件。

file_operations
/write compat_test.md "这是旧格式兼容测试"

已保存。'''
    _, results, ok = run_scenario(executor, "旧格式兼容（file_operations/write）", ai)
    scenarios.append(("compat", "旧格式兼容", ok, results))

    # ========== 场景16: 删除文件 ==========
    ai = '''用户要求删除测试文件。

【调用：delete_file({"path": "compat_test.md"})】

已删除。'''
    _, results, ok = run_scenario(executor, "删除文件", ai)
    scenarios.append(("delete_file", "删除文件", ok, results))

    # ========== 生成报告 ==========
    total = len(scenarios)
    passed = sum(1 for _, _, ok, _ in scenarios if ok)

    report_lines.append(f"\n## 汇总\n\n| 指标 | 数值 |\n|------|------|\n| 总场景 | {total} |\n| 通过 | {passed} |\n| 失败 | {total - passed} |\n")

    report_lines.append("\n## 详细结果\n")
    for tool, name, ok, results in scenarios:
        status = "✅ 通过" if ok else "❌ 失败"
        report_lines.append(f"\n### {name} (`{tool}`) — {status}")
        for r in results:
            report_lines.append(f"- {r}")

    report_lines.append("\n---\n\n## 工作空间文件清单\n")
    for fn in sorted(os.listdir(WORKSPACE)):
        fpath = os.path.join(WORKSPACE, fn)
        size = os.path.getsize(fpath)
        report_lines.append(f"- `{fn}` ({size} bytes)")

    report_lines.append("\n\n*报告生成完毕。*")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n{'='*60}")
    print(f"演示完成！")
    print(f"测试报告已保存到: {REPORT_FILE}")
    print(f"通过: {passed}/{total}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
