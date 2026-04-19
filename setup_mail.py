#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件账户配置向导
一键配置 ~/.zhipu_cli_config.json 中的邮件设置
"""
import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".zhipu_cli_config.json"

PRESETS = {
    "1": ("QQ邮箱", "imap.qq.com", "smtp.qq.com"),
    "2": ("163邮箱", "imap.163.com", "smtp.163.com"),
    "3": ("Gmail", "imap.gmail.com", "smtp.gmail.com"),
    "4": ("Outlook/Hotmail", "outlook.office365.com", "smtp.office365.com"),
    "5": ("阿里云邮箱", "imap.aliyun.com", "smtp.aliyun.com"),
    "6": ("自定义", None, None),
}

print("=" * 60)
print("  📧 凡人打字机 — 邮件账户配置向导")
print("=" * 60)
print()
print("请选择您的邮箱服务商：")
for k, (name, imap, smtp) in PRESETS.items():
    print(f"  {k}. {name}")
print()

choice = input("👉 输入编号 (1-6): ").strip()
if choice not in PRESETS:
    print("❌ 无效选择")
    exit(1)

name, imap_server, smtp_server = PRESETS[choice]

if choice == "6":
    imap_server = input("  IMAP 服务器地址: ").strip()
    smtp_server = input("  SMTP 服务器地址: ").strip()

email = input(f"  邮箱地址 (如 xxx@{name.replace('邮箱', '').lower()}.com): ").strip()
password = input("  密码/授权码: ").strip()

if not all([imap_server, smtp_server, email, password]):
    print("❌ 所有字段都必须填写")
    exit(1)

# 加载现有配置
cfg = {}
if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception:
        pass

cfg["mail"] = {
    "imap_server": imap_server,
    "smtp_server": smtp_server,
    "email": email,
    "password": password
}

with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)

print()
print("=" * 60)
print(f"  ✅ 邮件配置已保存到 {CONFIG_FILE}")
print("=" * 60)
print()
print("配置内容：")
print(f"  服务商: {name}")
print(f"  IMAP:   {imap_server}")
print(f"  SMTP:   {smtp_server}")
print(f"  邮箱:   {email}")
print(f"  密码:   {'*' * len(password)}")
print()
print("重启 fr-cli 后即可使用邮件功能：")
print("  【调用：mail_inbox({})】")
print("  【调用：mail_read({\"id\": \"1\"})】")
print("  【调用：mail_send({\"to\": \"...\", \"subject\": \"...\", \"body\": \"...\"})】")
print()
