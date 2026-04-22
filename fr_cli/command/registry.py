"""
统一工具注册表
所有内置命令与AI工具通过装饰器注册，实现单一入口、自动安全确认、参数校验。
"""


# ---- 触发关键词常量（避免同类工具重复定义）----
_TRIGGERS_FILE = ["文件", "目录", "folder", "读取", "read", "保存到", "save to", "写入文件", "创建文件", "生成文件", "ls", "cat", "cd", "write", "append", "delete"]
_TRIGGERS_WEB = ["搜索", "search", "查一下", "查询", "look up", "最新新闻", "今天天气", "股价", "汇率", "查百度", "查谷歌"]
_TRIGGERS_MAIL = ["邮件", "mail", "email", "发邮件", "收件箱", "inbox", "发送邮件", "查看邮件"]
_TRIGGERS_CRON = ["定时任务", "定时执行", "周期性执行", "cron job", "scheduled task", "定时器"]
_TRIGGERS_DISK = ["云盘", "上传文件", "下载文件", "cloud disk", "upload file", "download file", "云端"]
_TRIGGERS_SESSION = ["保存会话", "加载会话", "导出会话", "save session", "load session", "export session"]
_TRIGGERS_CONFIG = ["切换模型", "换模型", "改模型", "set model", "api key", "api密钥", "切换语言", "设置上限"]


class ToolRegistry:
    """工具注册表 —— 单一真相源"""

    def __init__(self):
        self._tools = {}      # name -> tool_info
        self._aliases = {}    # alias(without /) -> name

    def register(self, name, description="", params=None, security=None, aliases=None, needs_msgs=False, triggers=None):
        """装饰器：注册一个工具/命令"""
        def decorator(func):
            self._tools[name] = {
                "name": name,
                "description": description,
                "params": params or {},
                "security": security,
                "aliases": aliases or [],
                "needs_msgs": needs_msgs,
                "triggers": triggers or [],
                "handler": func,
            }
            for alias in (aliases or []):
                key = alias.lstrip("/")
                self._aliases[key] = name
            return func
        return decorator

    def _check_security(self, deps, security_key, target):
        if not security_key:
            return True
        if deps.security is None:
            return True  # 测试/非交互环境中无 security 时放行，由调用方保障安全
        return deps.security.check(security_key, target)

    def dispatch(self, deps, tool_name, msgs=None, skip_security=False, **kwargs):
        """结构化调用：tool_name + kwargs"""
        tool = self._tools.get(tool_name)
        if not tool:
            return None, f"Unknown tool: {tool_name}"

        # 参数校验
        for param, ptype in tool["params"].items():
            if param not in kwargs:
                return None, f"Missing required parameter: {param}"

        # 安全确认（仅当未显式跳过且声明了安全级别时）
        if not skip_security and tool["security"]:
            target = kwargs.get("path", tool_name)
            if not self._check_security(deps, tool["security"], target):
                return None, "Denied"

        try:
            if tool["needs_msgs"]:
                return tool["handler"](deps, msgs=msgs, **kwargs)
            return tool["handler"](deps, **kwargs)
        except Exception as e:
            return None, f"Error: {e}"

    def _dispatch_cmd_parts(self, deps, parts, msgs=None):
        """内部：根据已分词的 parts 调度命令（复用逻辑，避免重复 split）"""
        if not parts:
            return None, "Empty command"

        cmd = parts[0].lstrip("/")
        tool_name = self._aliases.get(cmd, cmd)
        tool = self._tools.get(tool_name)

        if not tool:
            return None, f"Unknown command: {cmd}"

        kwargs = self._parse_cmd_args(parts, tool, deps)
        if isinstance(kwargs, tuple) and len(kwargs) == 2 and kwargs[0] is None:
            return kwargs
        return self.dispatch(deps, tool_name, msgs=msgs, skip_security=True, **kwargs)

    def dispatch_cmd(self, deps, cmd_str, msgs=None):
        """命令字符串调用：/cmd args（跳过安全确认，由调用方负责）"""
        parts = cmd_str.strip().split()
        return self._dispatch_cmd_parts(deps, parts, msgs=msgs)

    def _parse_cmd_args(self, parts, tool, deps):
        """将命令行参数解析为 kwargs"""
        cmd = parts[0]
        arg1 = parts[1] if len(parts) > 1 else ""
        arg2 = parts[2] if len(parts) > 2 else ""
        name = tool["name"]

        # 文件操作
        if name in ("write_file", "append_file"):
            return {"path": arg1, "content": ' '.join(parts[2:]) if len(parts) > 2 else ""}
        if name == "read_file":
            return {"path": arg1}
        if name == "list_files":
            return {}
        if name == "change_dir":
            return {"path": arg1}
        if name == "delete_file":
            return {"path": arg1}

        # 图片
        if name == "analyze_image":
            return {"path": arg1, "text": arg2}
        if name == "generate_image":
            return {"prompt": arg1}

        # 网络
        if name == "search_web":
            return {"query": arg1}
        if name == "fetch_web":
            return {"url": arg1}

        # 邮件
        if name == "mail_inbox":
            return {}
        if name == "mail_read":
            return {"id": arg1}
        if name == "mail_send":
            body = ' '.join(parts[3:]) if len(parts) > 3 else ""
            return {"to": arg1, "subject": arg2, "body": body}
        if name == "mail_setup":
            return {}

        # 定时任务
        if name == "cron_add":
            return {"command": arg2, "interval": int(arg1) if arg1.isdigit() else 0}
        if name == "cron_list":
            return {}
        if name == "cron_del":
            return {"id": arg1}

        # 云盘
        if name == "disk_ls":
            return {}
        if name == "disk_up":
            return {"local": arg1, "remote": arg2}
        if name == "disk_down":
            return {"remote": arg1, "local": arg2}
        if name == "disk_setup":
            return {}

        # 会话
        if name == "save_session":
            return {"name": arg1}
        if name in ("list_sessions", "load_session"):
            return {}
        if name == "export_session":
            return {}
        if name == "delete_session":
            return {}

        # 配置
        if name == "set_model":
            return {"name": arg1}
        if name == "set_key":
            return {"key": arg1}
        if name == "set_limit":
            return {"limit": arg1}
        if name == "set_lang":
            return {"code": arg1}

        # 别名
        if name == "set_alias":
            return {"key": arg1, "value": arg2}

        # 撤销
        if name == "undo":
            return {}

        # 插件列表
        if name == "list_plugins":
            return {}

        # 更新
        if name == "update_check":
            return {}
        if name == "update_run":
            return {}

        # 本地应用启动
        if name == "open_file":
            return {"path": arg1}
        if name == "launch_app":
            return {"name": arg1, "target": ' '.join(parts[2:]) if len(parts) > 2 else None}
        if name == "list_apps":
            return {}

        # Agent 分身
        if name == "agent_create":
            return {"name": arg1, "description": ' '.join(parts[2:]) if len(parts) > 2 else ""}
        if name == "agent_run":
            return {"name": arg1}

        # 数据卷轴
        if name == "read_excel":
            return {"path": arg1}
        if name == "read_csv":
            return {"path": arg1}

        return {}

    def get_tools(self):
        return list(self._tools.values())

    def get_trigger_map(self):
        """获取工具触发关键词映射"""
        return {name: info["triggers"] for name, info in self._tools.items() if info.get("triggers")}

    def get_available_tools(self, plugins):
        """获取 AI 可用的工具列表（含插件）"""
        tools = []
        for t in self._tools.values():
            tools.append({
                "name": t["name"],
                "description": t["description"],
                "commands": [f"/{t['name']}"] + t["aliases"],
                "triggers": t.get("triggers", []),
            })
        for plugin_name in (plugins or {}):
            tools.append({
                "name": f"plugin_{plugin_name}",
                "description": f"自定义插件: {plugin_name}",
                "commands": [f"/{plugin_name}"],
                "triggers": [],
            })
        return tools


# ------------------------------------------------------------------
# 全局注册表实例
# ------------------------------------------------------------------
_registry = ToolRegistry()
register = _registry.register


def get_registry():
    return _registry


# ------------------------------------------------------------------
# Helper：确保子系统已配置
# ------------------------------------------------------------------
def _ensure_mail(deps):
    if deps.mail_c and getattr(deps.mail_c, "email", None) and getattr(deps.mail_c, "password", None) and getattr(deps.mail_c, "imap_server", None):
        return True
    from fr_cli.conf.wizard import mail_wizard
    ok, deps.cfg = mail_wizard(deps.cfg, deps.lang)
    if ok:
        from fr_cli.weapon.mail import MailClient
        deps.mail_c = MailClient(deps.cfg.get("mail", {}))
    return ok


def _ensure_disk(deps):
    if deps.disk_c and getattr(deps.disk_c, "type", None):
        return True
    from fr_cli.conf.wizard import disk_wizard
    ok, deps.cfg = disk_wizard(deps.cfg, deps.lang)
    if ok:
        from fr_cli.weapon.disk import CloudDisk
        deps.disk_c = CloudDisk(deps.cfg.get("disk", {}))
    return ok


# ------------------------------------------------------------------
# ========== 文件操作 ==========
# ------------------------------------------------------------------
@register(
    name="write_file",
    triggers=_TRIGGERS_FILE,
    description="写入文件",
    params={"path": str, "content": str},
    security="sec_write",
    aliases=["/write"],
)
def _write_file(deps, **kwargs):
    ok, msg = deps.vfs.write(kwargs["path"], kwargs["content"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="read_file",
    triggers=_TRIGGERS_FILE,
    description="读取文件",
    params={"path": str},
    security="sec_read",
    aliases=["/cat"],
)
def _read_file(deps, **kwargs):
    txt, err = deps.vfs.read(kwargs["path"], deps.lang)
    return (txt, None) if not err else (None, err)


@register(
    name="list_files",
    triggers=_TRIGGERS_FILE,
    description="列出文件",
    params={},
    aliases=["/ls"],
)
def _list_files(deps, **kwargs):
    items, err = deps.vfs.ls(deps.lang)
    return ("\n".join(items), None) if not err else (None, err)


@register(
    name="change_dir",
    triggers=_TRIGGERS_FILE,
    description="切换目录",
    params={"path": str},
    aliases=["/cd"],
)
def _change_dir(deps, **kwargs):
    ok, msg = deps.vfs.cd(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="append_file",
    triggers=_TRIGGERS_FILE,
    description="追加文件",
    params={"path": str, "content": str},
    security="sec_write",
    aliases=["/append"],
)
def _append_file(deps, **kwargs):
    ok, msg = deps.vfs.append(kwargs["path"], kwargs["content"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="delete_file",
    triggers=_TRIGGERS_FILE,
    description="删除文件",
    params={"path": str},
    security="sec_write",
    aliases=["/delete"],
)
def _delete_file(deps, **kwargs):
    ok, msg = deps.vfs.delete(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


# ------------------------------------------------------------------
# ========== 图片 ==========
# ------------------------------------------------------------------
@register(
    name="analyze_image",
    triggers=["分析图片", "识图", "看图", "describe image", "图片内容", "识别图片", "生成图片", "画图", "画一张"],
    description="图片分析",
    params={"path": str, "text": str},
    security="sec_read",
    aliases=["/see"],
    needs_msgs=True,
)
def _analyze_image(deps, msgs=None, **kwargs):
    from fr_cli.weapon.vision import prep_see_msg
    from fr_cli.core.stream import stream_cnt
    if not msgs:
        return None, "No message history available"
    prep_see_msg(msgs, kwargs["path"], kwargs.get("text", ""), vfs=deps.vfs)
    txt, _, response_time = stream_cnt(deps.client, deps.model_name, msgs, deps.lang)
    return f"图片分析结果:\n{txt}\n耗时: {response_time:.2f}秒", None


@register(
    name="generate_image",
    description="生成图片",
    params={"prompt": str},
    security="sec_gen_img",
)
def _generate_image(deps, **kwargs):
    from fr_cli.weapon.vision import gen_img
    out_dir = deps.vfs.cwd if deps.vfs else "."
    ok, res = gen_img(deps.client, kwargs["prompt"], out_dir, deps.lang)
    return (res, None) if ok else (None, res)


# ------------------------------------------------------------------
# ========== 网络 ==========
# ------------------------------------------------------------------
@register(
    name="search_web",
    triggers=_TRIGGERS_WEB,
    description="网络搜索",
    params={"query": str},
    security="sec_fetch_web",
    aliases=["/web"],
)
def _search_web(deps, **kwargs):
    res, err = deps.web_c.search(kwargs["query"], deps.lang)
    if err:
        return None, err
    return "\n".join([f"- {r['title']}\n  {r['url']}\n  {r['snippet'][:50]}..." for r in res]), None


@register(
    name="fetch_web",
    triggers=_TRIGGERS_WEB,
    description="抓取网页",
    params={"url": str},
    security="sec_fetch_web",
    aliases=["/fetch"],
)
def _fetch_web(deps, **kwargs):
    txt, err = deps.web_c.fetch(kwargs["url"], deps.lang)
    return (txt, None) if not err else (None, err)


# ------------------------------------------------------------------
# ========== 邮件 ==========
# ------------------------------------------------------------------
@register(
    name="mail_inbox",
    triggers=_TRIGGERS_MAIL,
    description="查看收件箱",
    params={},
    aliases=["/mail_inbox"],
)
def _mail_inbox(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_mail(deps):
        return None, T("mail_no_cfg", deps.lang)
    mails, err = deps.mail_c.inbox(deps.lang)
    if err:
        return None, err
    return "\n".join([f"{m['id']} {m['sub'][:30]} ({m['from']})" for m in mails]), None


@register(
    name="mail_read",
    triggers=_TRIGGERS_MAIL,
    description="读取邮件",
    params={"id": str},
    aliases=["/mail_read"],
)
def _mail_read(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_mail(deps):
        return None, T("mail_no_cfg", deps.lang)
    m, err = deps.mail_c.read(kwargs["id"], deps.lang)
    if err:
        return None, err
    return f"{m['sub']}\n{m['from']} | {m['date']}\n\n{m['body']}", None


@register(
    name="mail_send",
    triggers=_TRIGGERS_MAIL,
    description="发送邮件",
    params={"to": str, "subject": str, "body": str},
    security="sec_send_mail",
    aliases=["/mail_send"],
)
def _mail_send(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_mail(deps):
        return None, T("mail_no_cfg", deps.lang)
    ok, err = deps.mail_c.send(kwargs["to"], kwargs["subject"], kwargs["body"], deps.lang)
    return (T("mail_ok", deps.lang), None) if ok else (None, err or "Send failed")


@register(
    name="mail_setup",
    description="邮件配置向导",
    params={},
    aliases=["/mail_setup"],
)
def _mail_setup(deps, **kwargs):
    from fr_cli.conf.wizard import mail_wizard
    ok, deps.cfg = mail_wizard(deps.cfg, deps.lang)
    if ok:
        from fr_cli.weapon.mail import MailClient
        deps.mail_c = MailClient(deps.cfg.get("mail", {}))
    return ("OK", None) if ok else (None, "Cancelled")


# ------------------------------------------------------------------
# ========== 定时任务 ==========
# ------------------------------------------------------------------
@register(
    name="cron_add",
    triggers=_TRIGGERS_CRON,
    description="添加定时任务",
    params={"command": str, "interval": int},
    security="sec_exec",
    aliases=["/cron_add"],
)
def _cron_add(deps, **kwargs):
    from fr_cli.weapon.cron import add_job, _default_manager
    from fr_cli.gatekeeper.manager import sync_gatekeeper_cron_jobs
    jid, m = add_job(kwargs["command"], kwargs["interval"], deps.lang)
    if jid is not None:
        # 自动同步到 gatekeeper 配置
        sync_gatekeeper_cron_jobs(cron_jobs=_default_manager.export_jobs())
        return m, None
    return None, m


@register(
    name="cron_list",
    triggers=_TRIGGERS_CRON,
    description="列出定时任务",
    params={},
    aliases=["/cron_list"],
)
def _cron_list(deps, **kwargs):
    from fr_cli.weapon.cron import list_jobs
    res, err = list_jobs(deps.lang)
    return ("\n".join(res), None) if not err else (None, err)


@register(
    name="cron_del",
    triggers=_TRIGGERS_CRON,
    description="删除定时任务",
    params={"id": str},
    aliases=["/cron_del"],
)
def _cron_del(deps, **kwargs):
    from fr_cli.weapon.cron import del_job, _default_manager
    from fr_cli.gatekeeper.manager import sync_gatekeeper_cron_jobs
    ok, m = del_job(int(kwargs["id"]), deps.lang)
    if ok:
        # 自动同步到 gatekeeper 配置
        sync_gatekeeper_cron_jobs(cron_jobs=_default_manager.export_jobs())
        return m, None
    return None, m


# ------------------------------------------------------------------
# ========== 云盘 ==========
# ------------------------------------------------------------------
@register(
    name="disk_ls",
    triggers=_TRIGGERS_DISK,
    description="列出云盘文件",
    params={},
    aliases=["/disk_ls"],
)
def _disk_ls(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return None, T("disk_no_cfg", deps.lang)
    res, err = deps.disk_c.ls(deps.lang)
    return ("\n".join(res) if res else T("empty", deps.lang), None) if not err else (None, err)


@register(
    name="disk_up",
    triggers=_TRIGGERS_DISK,
    description="上传文件到云盘",
    params={"local": str, "remote": str},
    security="sec_upload_disk",
    aliases=["/disk_up"],
)
def _disk_up(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return None, T("disk_no_cfg", deps.lang)
    ok, m = deps.disk_c.up(kwargs["remote"], kwargs["local"], deps.lang)
    return (m, None) if ok else (None, m)


@register(
    name="disk_down",
    triggers=_TRIGGERS_DISK,
    description="从云盘下载文件",
    params={"remote": str, "local": str},
    security="sec_download_disk",
    aliases=["/disk_down"],
)
def _disk_down(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return None, T("disk_no_cfg", deps.lang)
    loc = kwargs.get("local") or kwargs["remote"].split("/")[-1]
    ok, m = deps.disk_c.down(kwargs["remote"], loc, deps.lang)
    return (m, None) if ok else (None, m)


@register(
    name="disk_cd",
    triggers=_TRIGGERS_DISK,
    description="切换云盘目录",
    params={"path": str},
    aliases=["/disk_cd"],
)
def _disk_cd(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not _ensure_disk(deps):
        return None, T("disk_no_cfg", deps.lang)
    ok, msg = deps.disk_c.cd(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="disk_setup",
    description="云盘配置向导",
    params={},
    aliases=["/disk_setup"],
)
def _disk_setup(deps, **kwargs):
    from fr_cli.conf.wizard import disk_wizard
    ok, deps.cfg = disk_wizard(deps.cfg, deps.lang)
    if ok:
        from fr_cli.weapon.disk import CloudDisk
        deps.disk_c = CloudDisk(deps.cfg.get("disk", {}))
    return ("OK", None) if ok else (None, "Cancelled")


# ------------------------------------------------------------------
# ========== 会话管理 ==========
# ------------------------------------------------------------------
@register(
    name="save_session",
    triggers=_TRIGGERS_SESSION,
    description="保存会话",
    params={"name": str},
    aliases=["/save"],
    needs_msgs=True,
)
def _save_session(deps, msgs=None, **kwargs):
    from fr_cli.memory.history import save_sess
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    sn = kwargs["name"]
    deps.cfg["session_name"] = sn
    save_config(deps.cfg)
    if save_sess(sn, msgs):
        return T('ok_sess_save', deps.lang, sn), None
    return None, "Save failed"


@register(
    name="list_sessions",
    triggers=_TRIGGERS_SESSION,
    description="列出会话",
    params={},
    aliases=["/load"],
)
def _list_sessions(deps, **kwargs):
    from fr_cli.memory.history import get_sessions
    from fr_cli.lang.i18n import T
    ss = get_sessions()
    if not ss:
        return None, T("no_sess", deps.lang)
    return "\n".join([f"[{i}] {s['name']}" for i, s in enumerate(ss)]), None


@register(
    name="export_session",
    triggers=_TRIGGERS_SESSION,
    description="导出会话",
    params={},
    aliases=["/export"],
    needs_msgs=True,
)
def _export_session(deps, msgs=None, **kwargs):
    from fr_cli.memory.history import export_md
    from fr_cli.lang.i18n import T
    out_dir = deps.vfs.cwd if deps.vfs else None
    ok, path = export_md(msgs, deps.lang, out_dir)
    return (T('ok_export', deps.lang, path), None) if ok else (None, "Export failed")


@register(
    name="delete_session",
    description="删除会话",
    params={"id": str},
    aliases=["/del"],
)
def _delete_session(deps, **kwargs):
    from fr_cli.memory.history import get_sessions, del_sess
    from fr_cli.lang.i18n import T
    ss = get_sessions()
    if not ss:
        return None, T("no_sess", deps.lang)
    sid = kwargs.get("id", "")
    if sid and sid.isdigit():
        idx = int(sid)
    else:
        idx = 0
    ok = del_sess(idx)
    return (T('ok_sess_del', deps.lang), None) if ok else (None, "Delete failed")


# ------------------------------------------------------------------
# ========== 配置管理 ==========
# ------------------------------------------------------------------
@register(
    name="set_model",
    triggers=_TRIGGERS_CONFIG,
    description="切换模型",
    params={"name": str},
    aliases=["/model"],
)
def _set_model(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    deps.cfg["model"] = kwargs["name"]
    deps.model_name = kwargs["name"]
    save_config(deps.cfg)
    return T('ok_model', deps.lang, kwargs["name"]), None


@register(
    name="set_key",
    triggers=_TRIGGERS_CONFIG,
    description="设置API密钥",
    params={"key": str},
    aliases=["/key"],
)
def _set_key(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    deps.cfg["key"] = kwargs["key"]
    save_config(deps.cfg)
    return T('ok_key', deps.lang), None


@register(
    name="set_limit",
    triggers=_TRIGGERS_CONFIG,
    description="设置Token上限",
    params={"limit": int},
    aliases=["/limit"],
)
def _set_limit(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    lim = int(kwargs["limit"])
    if lim < 1000:
        return None, T('err_limit', deps.lang)
    deps.cfg["limit"] = lim
    save_config(deps.cfg)
    return T('ok_limit', deps.lang, lim), None


@register(
    name="set_lang",
    triggers=_TRIGGERS_CONFIG,
    description="切换语言",
    params={"code": str},
    aliases=["/lang"],
)
def _set_lang(deps, **kwargs):
    from fr_cli.conf.config import save_config
    lc = kwargs["code"]
    if lc in ['zh', 'en']:
        deps.cfg["lang"] = lc
        deps.lang = lc
        save_config(deps.cfg)
        return f"Language changed to {lc}", None
    return None, "Invalid language. Use zh or en"


@register(
    name="set_alias",
    description="设置命令别名",
    params={"key": str, "value": str},
    aliases=["/alias"],
)
def _set_alias(deps, **kwargs):
    from fr_cli.conf.config import save_config
    from fr_cli.lang.i18n import T
    k, v = kwargs["key"], kwargs.get("value", "")
    if v:
        aliases = deps.cfg.get("aliases", {})
        aliases[k] = v
        deps.cfg["aliases"] = aliases
        save_config(deps.cfg)
        return T('ok_alias_set', deps.lang, k, v), None
    val = deps.cfg.get("aliases", {}).get(k, "")
    return val if val else T("no_alias", deps.lang), None


# ------------------------------------------------------------------
# ========== 其他 ==========
# ------------------------------------------------------------------
@register(
    name="undo",
    description="撤销最近一轮对话",
    params={},
    aliases=["/undo"],
    needs_msgs=True,
)
def _undo(deps, msgs=None, **kwargs):
    from fr_cli.lang.i18n import T
    if len(msgs) > 1 and msgs[-1]["role"] == "assistant":
        msgs.pop()
        return T('ok_undo', deps.lang), None
    if len(msgs) > 1 and msgs[-1]["role"] == "user":
        msgs.pop()
        return T('ok_undo', deps.lang), None
    return None, T('err_undo', deps.lang)


@register(
    name="list_plugins",
    description="列出已安装插件",
    params={},
    aliases=["/skills"],
)
def _list_plugins(deps, **kwargs):
    from fr_cli.lang.i18n import T
    if not deps.plugins:
        return None, T("no_plugins", deps.lang)
    return "\n".join([f"/{k}" for k in deps.plugins.keys()]), None


@register(
    name="update_check",
    description="检查更新",
    params={},
    aliases=["/update_check"],
)
def _update_check(deps, **kwargs):
    from fr_cli.breakthrough.update import update_check
    ok, info, err = update_check(verbose=False)
    if err:
        return None, f"检查失败: {err}"
    if not ok:
        return "当前已是最新版本。", None
    ver = info.get("version", "?")
    note = info.get("release_note", "")
    return f"发现新版本: {ver}\n{note}", None


@register(
    name="update_run",
    description="执行更新",
    params={},
    aliases=["/update_run"],
)
def _update_run(deps, **kwargs):
    from fr_cli.breakthrough.update import update_and_restart
    ok, msg = update_and_restart(verbose=True, allow_restart=True)
    return (msg, None) if ok else (None, msg)


# ------------------------------------------------------------------
# ========== 本地应用启动器 ==========
# ------------------------------------------------------------------
@register(
    name="open_file",
    triggers=["打开", "open", "启动", "launch", "浏览", "播放", "查看"],
    description="用系统默认程序打开文件或 URL",
    params={"path": str},
    aliases=["/open"],
)
def _open_file(deps, **kwargs):
    from fr_cli.weapon.launcher import open_file
    ok, msg = open_file(kwargs["path"], deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="launch_app",
    triggers=["打开应用", "启动程序", "运行软件", "launch app", "打开微信", "打开浏览器", "打开 Word", "打开 Excel"],
    description="启动指定应用程序，可带文件或 URL 参数",
    params={"name": str},
    aliases=["/launch"],
)
def _launch_app(deps, **kwargs):
    from fr_cli.weapon.launcher import launch_app
    ok, msg = launch_app(kwargs["name"], kwargs.get("target"), deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="list_apps",
    description="列出本机可用应用别名",
    params={},
    aliases=["/apps"],
)
def _list_apps(deps, **kwargs):
    from fr_cli.weapon.launcher import list_apps
    res, err = list_apps(deps.lang)
    return (res, None) if not err else (None, err)


# ------------------------------------------------------------------
# ========== Agent 分身系统 ==========
# ------------------------------------------------------------------
@register(
    name="agent_create",
    triggers=["创建Agent", "新建Agent", "生成Agent", "create agent", "new agent"],
    description="根据需求自动生成 Agent 分身",
    params={"name": str, "description": str},
    aliases=["/agent_create"],
)
def _agent_create(deps, **kwargs):
    from fr_cli.agent.generator import generate_agent
    from fr_cli.agent.manager import save_persona, save_skills, save_agent_code, create_agent_dir
    name = kwargs["name"]
    desc = kwargs["description"]
    d = create_agent_dir(name)
    result = generate_agent(deps.client, deps.model_name, name, desc, deps.lang)
    if result["persona"]:
        save_persona(name, result["persona"])
    if result["skills"]:
        save_skills(name, result["skills"])
    if result["code"]:
        save_agent_code(name, result["code"])
    return f"Agent [{name}] 铸造完成！路径: {d}", None


@register(
    name="agent_run",
    triggers=["运行Agent", "调用Agent", "执行Agent", "run agent"],
    description="运行指定本地 Agent",
    params={"name": str},
    aliases=["/agent_run"],
)
def _agent_run(deps, **kwargs):
    from fr_cli.agent.executor import run_agent
    class _CompatState:
        def __init__(self, d):
            for k, v in d.__dict__.items():
                setattr(self, k, v)
    compat = _CompatState(deps)
    compat.executor = getattr(deps, 'executor', None)
    result, err = run_agent(kwargs["name"], compat)
    return (result, None) if not err else (None, err)


@register(
    name="agent_call",
    triggers=["调用Agent", "协作Agent", "agent_call", "召唤Agent"],
    description="调用Agent（本地或远程）并传入任务描述，实现MasterAgent与其他Agent协作",
    params={"name": str, "user_input": str},
    aliases=["/agent_call"],
)
def _agent_call(deps, **kwargs):
    """MasterAgent 调用其他 Agent（支持本地和远程）"""
    from fr_cli.agent.client import call_agent
    class _CompatState:
        def __init__(self, d):
            for k, v in d.__dict__.items():
                setattr(self, k, v)
    compat = _CompatState(deps)
    compat.executor = getattr(deps, 'executor', None)
    result, err = call_agent(kwargs["name"], compat, user_input=kwargs.get("user_input", ""))
    return (result, None) if not err else (None, err)


# ------------------------------------------------------------------
# ========== 数据卷轴（Excel / CSV）==========
# ------------------------------------------------------------------
@register(
    name="read_excel",
    triggers=["Excel", "表格", "xlsx", "读取Excel", "分析表格"],
    description="读取 Excel 文件并返回数据摘要",
    params={"path": str},
    security="sec_read",
    aliases=["/read_excel"],
)
def _read_excel(deps, **kwargs):
    from fr_cli.weapon.dataframe import read_excel
    res, err = read_excel(kwargs["path"], lang=deps.lang)
    return (res, None) if not err else (None, err)


@register(
    name="read_csv",
    triggers=["CSV", "csv", "读取CSV", "分析CSV"],
    description="读取 CSV 文件并返回数据摘要",
    params={"path": str},
    security="sec_read",
    aliases=["/read_csv"],
)
def _read_csv(deps, **kwargs):
    from fr_cli.weapon.dataframe import read_csv
    res, err = read_csv(kwargs["path"], lang=deps.lang)
    return (res, None) if not err else (None, err)
