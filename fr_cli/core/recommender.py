"""
智能功能推荐系统
根据用户输入推荐相关功能，按使用频率排序
"""
import json
from pathlib import Path

_COMMAND_USAGE_FILE = Path.home() / ".fr_cli" / "command_usage.json"


def _load_usage():
    if _COMMAND_USAGE_FILE.exists():
        try:
            with open(_COMMAND_USAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_usage(usage):
    _COMMAND_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_COMMAND_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, indent=2, ensure_ascii=False)


def record_command_usage(cmd):
    """记录命令使用频率"""
    usage = _load_usage()
    usage[cmd] = usage.get(cmd, 0) + 1
    _save_usage(usage)


def _base_cmd(cmd_str):
    """提取命令字符串中的基础命令（去掉参数）"""
    return cmd_str.split()[0] if cmd_str else ""


def recommend_features(user_input):
    """根据用户输入推荐相关功能，按使用频率排序"""
    usage = _load_usage()
    recommendations = []
    input_lower = user_input.lower()

    # 文件相关
    if any(kw in input_lower for kw in ['文件', 'file', '目录', 'folder', '读取', 'read', '查看', 'view', 'ls', 'cat']):
        recommendations.append({"cmd": "/ls", "desc": "列出当前目录文件"})
        recommendations.append({"cmd": "/cat <file>", "desc": "查看文件内容"})
        recommendations.append({"cmd": "/cd <dir>", "desc": "切换目录"})

    # 文件写入相关
    if any(kw in input_lower for kw in ['保存', '写入', 'write', '创建', 'create', '生成', 'generate']):
        recommendations.append({"cmd": "/write <file> <content>", "desc": "写入文件内容"})
        recommendations.append({"cmd": "/append <file> <content>", "desc": "追加文件内容"})

    # 图片相关
    if any(kw in input_lower for kw in ['图片', 'image', 'photo', '看图', 'see', '识别', 'recognize']):
        recommendations.append({"cmd": "/see <image>", "desc": "查看并分析图片"})

    # 邮件相关
    if any(kw in input_lower for kw in ['邮件', 'mail', 'email', '发送', 'send', '收件', 'inbox']):
        recommendations.append({"cmd": "/mail_inbox", "desc": "查看收件箱"})
        recommendations.append({"cmd": "/mail_send <to> <subject>", "desc": "发送邮件"})

    # 网络搜索相关
    if any(kw in input_lower for kw in ['搜索', 'search', 'web', '网页', 'website', '查询', 'query']):
        recommendations.append({"cmd": "/web <query>", "desc": "网络搜索"})
        recommendations.append({"cmd": "/fetch <url>", "desc": "获取网页内容"})

    # 定时任务相关
    if any(kw in input_lower for kw in ['定时', 'schedule', 'cron', '任务', 'task', '周期', 'period']):
        recommendations.append({"cmd": "/cron_add <seconds> <command>", "desc": "添加定时任务"})
        recommendations.append({"cmd": "/cron_list", "desc": "列出定时任务"})

    # 云盘相关
    if any(kw in input_lower for kw in ['云盘', 'cloud', '上传', 'upload', '下载', 'download', 'disk']):
        recommendations.append({"cmd": "/disk_ls", "desc": "列出云盘文件"})
        recommendations.append({"cmd": "/disk_up <local> <remote>", "desc": "上传到云盘"})
        recommendations.append({"cmd": "/disk_down <remote> <local>", "desc": "从云盘下载"})

    # 会话相关
    if any(kw in input_lower for kw in ['保存会话', 'save session', '加载会话', 'load session', '会话', 'session', '记录', 'record']):
        recommendations.append({"cmd": "/save <name>", "desc": "保存当前会话"})
        recommendations.append({"cmd": "/load", "desc": "加载历史会话"})

    # 配置相关
    if any(kw in input_lower for kw in ['模型', 'model', '密钥', 'key', '配置', 'config', '设置', 'setting']):
        recommendations.append({"cmd": "/model <name>", "desc": "切换AI模型"})
        recommendations.append({"cmd": "/key <key>", "desc": "设置API密钥"})
        recommendations.append({"cmd": "/lang <zh/en>", "desc": "切换语言"})

    # 插件相关
    if any(kw in input_lower for kw in ['插件', 'plugin', '技能', 'skill', '工具', 'tool']):
        recommendations.append({"cmd": "/skills", "desc": "查看可用插件"})

    # 导出相关
    if any(kw in input_lower for kw in ['导出', 'export', '文档', 'document']):
        recommendations.append({"cmd": "/export", "desc": "导出会话为Markdown"})

    # 命令执行相关
    if any(kw in input_lower for kw in ['执行', 'exec', '命令', 'command', 'shell', 'bash', 'terminal']):
        recommendations.append({"cmd": "!<command>", "desc": "执行系统命令"})
        recommendations.append({"cmd": "!<cmd> | <prompt>", "desc": "命令输出管道到AI"})

    # 按使用频率排序（频率高的置顶）
    recommendations.sort(key=lambda x: usage.get(_base_cmd(x["cmd"]), 0), reverse=True)
    return recommendations
