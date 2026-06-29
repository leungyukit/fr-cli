"""
fr_cli command 参数解析器

将 /cmd arg1 arg2 ... 形式的参数解析为对应工具的 kwargs。

设计:
- 单一入口 parse_cmd_args(parts, tool, deps) → dict
- 内部按工具名 dispatch 到独立函数,便于扩展和阅读
- 原有 _parse_cmd_args 行为完全保留(向后兼容,测试无变化)

按工具类别分:
- 文件操作:write_file / append_file / read_file / list_files / change_dir / delete_file / rename / replace / grep
- 图片 / OCR:analyze_image / generate_image / ocr_recognize
- 网络:search_web / fetch_web / ping_host / port_scan / ip_scan / ssh_command / scp_transfer
- 邮件:mail_inbox / mail_read / mail_send / mail_search
- M365:m365_inbox / m365_read / m365_send / m365_search
- 文件转换:pdf_to_text / docx_to_text / excel_to_text
- Web 书签 / RAG:web_bookmark / rag_dir / rag_query
- 工作流:swarm_*
- Defi:crypto / defi_pool_chart
- Charts / 其他
"""
from __future__ import annotations

from typing import Any, Dict, List


def parse_cmd_args(parts: List[str], tool: Dict[str, Any], deps: Any) -> Dict[str, Any]:
    """将命令行参数解析为 kwargs(原 ToolRegistry._parse_cmd_args)

    Args:
        parts: 命令分词列表(parts[0] 是命令名本身,如 "/ls")
        tool: 工具元数据 dict(包含 name / params / handler 等)
        deps: AppState 依赖命名空间(plugins / vfs / cfg 等)

    Returns:
        给工具 handler 用的 kwargs dict
    """
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
    if name == "rename_file":
        return {"old_path": arg1, "new_path": arg2}
    if name == "replace_text":
        return {
            "path": arg1,
            "old_text": arg2,
            "new_text": parts[3] if len(parts) > 3 else "",
            "use_regex": parts[4].lower() in ("true", "1", "yes") if len(parts) > 4 else False,
        }
    if name == "grep_text":
        return {
            "path": arg1,
            "pattern": arg2,
            "use_regex": parts[3].lower() in ("true", "1", "yes") if len(parts) > 3 else False,
        }

    # 图片 / OCR
    if name == "analyze_image":
        return {"path": arg1, "text": arg2}
    if name == "generate_image":
        return {"prompt": arg1}
    if name == "ocr_recognize":
        return {"path": arg1}

    # 网络
    if name == "search_web":
        return {"query": arg1}
    if name == "fetch_web":
        return {"url": arg1}
    if name == "ping_host":
        return {"host": arg1}
    if name == "port_scan":
        return {"host": arg1, "ports": arg2}
    if name == "ip_scan":
        return {"network": arg1}
    if name == "network_devices":
        return {"network": arg1}
    if name == "ssh_command":
        return {"host": arg1, "user": arg2, "command": ' '.join(parts[3:]) if len(parts) > 3 else ""}
    if name == "scp_transfer":
        kwargs = {"host": arg1, "user": arg2}
        if len(parts) > 3:
            kwargs["local_path"] = parts[3]
        if len(parts) > 4:
            kwargs["remote_path"] = parts[4]
        if len(parts) > 5:
            kwargs["direction"] = parts[5]
        return kwargs

    # 邮件
    if name == "mail_inbox":
        return {}
    if name == "mail_read":
        return {"id": arg1}
    if name == "mail_send":
        body = ' '.join(parts[3:]) if len(parts) > 3 else ""
        return {"to": arg1, "subject": arg2, "body": body}
    if name == "mail_search":
        return {"query": arg1, "limit": int(parts[2]) if len(parts) > 2 else 20}

    # M365
    if name == "m365_inbox":
        return {}
    if name == "m365_read":
        return {"id": arg1}
    if name == "m365_send":
        body = ' '.join(parts[3:]) if len(parts) > 3 else ""
        return {"to": arg1, "subject": arg2, "body": body}
    if name == "m365_search":
        return {"query": arg1, "limit": int(parts[2]) if len(parts) > 2 else 20}

    # 文件转换
    if name == "pdf_to_text":
        return {"path": arg1}
    if name == "docx_to_text":
        return {"path": arg1}
    if name == "excel_to_text":
        return {"path": arg1}
    if name == "text_to_pdf":
        return {"content": arg1, "output": arg2}
    if name == "md_to_pdf":
        return {"path": arg1, "output": arg2}

    # 工作流 / swarm
    if name == "swarm_run":
        # /swarm <mode> <names,csv> <user_input...>
        if len(parts) < 3:
            return {"mode": "parallel", "names": [], "user_input": ""}
        mode = parts[1].lower()
        names = [n.strip() for n in parts[2].split(",") if n.strip()]
        user_input = " ".join(parts[3:]) if len(parts) > 3 else ""
        return {"mode": mode, "names": names, "user_input": user_input}

    # 蜂群 Agent_call
    if name == "agent_call":
        return {"name": arg1, "user_input": ' '.join(parts[2:]) if len(parts) > 2 else ""}

    # agent_create / agent_forge / agent_list 等
    if name == "agent_create":
        return {"name": arg1, "description": ' '.join(parts[2:]) if len(parts) > 2 else ""}
    if name == "agent_forge":
        return {"name": arg1}
    if name == "agent_run":
        return {"name": arg1, "input": ' '.join(parts[2:]) if len(parts) > 2 else ""}
    if name == "agent_delete":
        return {"name": arg1}
    if name == "agent_list":
        return {}
    if name == "agent_set_persona":
        return {"name": arg1, "content": ' '.join(parts[2:]) if len(parts) > 2 else ""}
    if name == "agent_set_skills":
        return {"name": arg1, "content": ' '.join(parts[2:]) if len(parts) > 2 else ""}
    if name == "agent_set_memory":
        return {"name": arg1, "content": ' '.join(parts[2:]) if len(parts) > 2 else ""}
    if name == "agent_show":
        return {"name": arg1}

    # 模型与配置
    if name == "set_model":
        return {"name": arg1}
    if name == "set_key":
        return {"key": arg1}
    if name == "set_limit":
        try:
            return {"limit": int(arg1)}
        except ValueError:
            return {"limit": 4096}
    if name == "set_lang":
        return {"code": arg1}
    if name == "model_current":
        return {}
    if name == "model_list":
        return {}

    # 会话
    if name == "save_session":
        return {"name": arg1}
    if name == "load_session":
        try:
            return {"idx": int(arg1)}
        except ValueError:
            return {"name": arg1}
    if name == "session_list":
        return {}
    if name == "session_delete":
        try:
            return {"idx": int(arg1)}
        except ValueError:
            return {"name": arg1}
    if name == "export_session":
        return {}
    if name == "rename_session":
        return {"name": arg1}

    # Cron
    if name == "cron_add":
        kwargs = {"command": arg1}
        if len(parts) > 2:
            try:
                kwargs["interval"] = int(parts[2])
            except ValueError:
                kwargs["interval"] = 60
        else:
            kwargs["interval"] = 60
        return kwargs
    if name == "cron_list":
        return {}
    if name == "cron_del":
        return {"id": arg1}
    if name == "cron_pause":
        return {"id": arg1}
    if name == "cron_resume":
        return {"id": arg1}

    # Web 书签 / RAG
    if name == "web_bookmark":
        kwargs = {"url": arg1}
        if len(parts) > 2:
            kwargs["title"] = parts[2]
        return kwargs
    if name == "web_bookmark_list":
        return {}
    if name == "web_bookmark_search":
        return {"query": arg1}
    if name == "rag_dir":
        return {"path": arg1}
    if name == "rag_sync":
        return {"path": arg1}
    if name == "rag_query":
        return {"query": arg1}
    if name == "rag_stats":
        return {}

    # Web 控制台
    if name == "console_start":
        kwargs = {"port": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 7777}
        return kwargs
    if name == "console_stop":
        return {}

    # DeFi / Crypto
    if name == "crypto_price":
        return {"symbol": arg1}
    if name == "crypto_balance":
        return {"address": arg1, "chain": arg2 or "ethereum"}
    if name == "crypto_tx":
        return {"tx_hash": arg1, "chain": arg2 or "ethereum"}
    if name == "defi_pools":
        return {"protocol": arg1, "limit": int(parts[2]) if len(parts) > 2 else 20}
    if name == "defi_pool":
        return {"pool_id": arg1}
    if name == "defi_apr":
        return {"pool_id": arg1}
    if name == "defi_search":
        return {"query": arg1}
    if name == "defi_history":
        return {"pool_id": arg1, "days": int(parts[2]) if len(parts) > 2 else 30}
    if name == "defi_compare":
        return {"pool_ids": arg1}
    if name == "defi_pool_chart":
        kwargs = {"pool_id": arg1, "period": "1Y", "width": 50}
        for tok in parts[2:]:
            if tok.startswith("--period="):
                kwargs["period"] = tok.split("=", 1)[1]
            elif tok.startswith("--width="):
                try:
                    kwargs["width"] = int(tok.split("=", 1)[1])
                except Exception:
                    pass
        return kwargs
    if name == "tts_local":
        return {"text": ' '.join(parts[1:]) if len(parts) > 1 else ""}
    if name == "tts_stream":
        return {"text": ' '.join(parts[1:]) if len(parts) > 1 else ""}

    # Streamlit / Web
    if name == "stock_query":
        return {"query": ' '.join(parts[1:]) if len(parts) > 1 else ""}
    if name == "stock_price":
        return {"code": arg1}
    if name == "stock_buy":
        try:
            return {"code": arg1, "price": float(parts[2]), "shares": int(parts[3])}
        except (ValueError, IndexError):
            return {"code": arg1}

    # 通用:按 params 顺序赋值
    params_meta = tool.get("params") or {}
    if params_meta:
        ordered = list(params_meta.keys())
        kwargs = {}
        for i, pname in enumerate(ordered):
            idx = i + 1
            if idx < len(parts):
                val = parts[idx]
                # 类型转换
                ann = params_meta[pname]
                if ann is int:
                    try:
                        val = int(val)
                    except ValueError:
                        val = 0
                elif ann is float:
                    try:
                        val = float(val)
                    except ValueError:
                        val = 0.0
                elif ann is bool:
                    val = val.lower() in ("true", "1", "yes")
                kwargs[pname] = val
        # 布尔标志 (--foo)
        for tok in parts:
            if tok.startswith("--async"):
                kwargs["async"] = False
        return kwargs

    return {}


__all__ = ["parse_cmd_args"]
