"""
选品洞察命令
/insight      — 主入口(查看 / 运行 / 历史)
/insight_extract — 立即提炼(等价于 /insight extract)

用法:
  /insight                         — 显示最新选品洞察
  /insight show                    — 同上,显式查看
  /insight extract [options]       — 立即跑一次提炼
    --source <mock|json|csv>        数据源类型(默认走 get_default_source)
    --path <file>                   数据文件路径(配合 json/csv 源)
    --since <YYYY-MM-DD>            只看此日期之后的记录
    --batch <N>                     每批提炼条数(默认 30)
  /insight history [N]             — 查看最近 N 条历史快照(默认 5)
  /insight sources                 — 列出可用数据源
"""
from fr_cli.ui.output import (
    success, failure, warning, info, header, kv_block
)


def _print_insights(payload, state):
    """把一份洞察 dict 打印到终端"""
    if not payload:
        warning("暂无选品洞察", detail="运行 /insight extract 跑一次提炼")
        return
    insights = payload.get("insights") or {}
    if not insights:
        warning("洞察档案为空")
        return

    header("最新选品洞察")
    kv_block([
        ("提炼时间", payload.get("created_at", "?")),
        ("数据源", payload.get("source_name", "?")),
        ("记录数", str(payload.get("record_count", "?"))),
    ])

    summary = (insights.get("summary") or "").strip()
    if summary:
        info("核心规律")
        print(f"  {summary}\n")

    categories = insights.get("categories") or []
    if categories:
        info("强势品类")
        for c in categories[:5]:
            if not isinstance(c, dict):
                continue
            print(f"  • {c.get('name', '?')} [{c.get('hit_rate', '?')}] — {c.get('evidence', '')}")
            ks = c.get("key_signals") or []
            if ks:
                for s in ks[:3]:
                    print(f"      ↪ {s}")
        print()

    price_bands = insights.get("price_bands") or []
    if price_bands:
        info("价格带规律")
        for p in price_bands[:4]:
            if not isinstance(p, dict):
                continue
            print(f"  • {p.get('range', '?')}: {p.get('verdict', '')} ({p.get('evidence', '')})")
        print()

    lc = insights.get("lifecycle_patterns") or []
    if lc:
        info("生命周期")
        for x in lc[:3]:
            if not isinstance(x, dict):
                continue
            print(f"  • {x.get('pattern', '?')}: {x.get('description', '')}")
        print()

    st = insights.get("seasonal_trends") or []
    if st:
        info("季节/时间信号")
        for x in st[:3]:
            if not isinstance(x, dict):
                continue
            print(f"  • {x.get('signal', '?')}: {x.get('evidence', '')}")
        print()

    ks = insights.get("key_signals") or []
    if ks:
        info("关键信号")
        for s in ks[:5]:
            print(f"  • {s}")


def _cmd_insight(state, parts):
    """/insight 主命令"""
    sub = parts[1].lower() if len(parts) > 1 else "show"
    args = parts[2:]

    # ------ 列表数据源 ------
    if sub == "sources":
        from fr_cli.agent.insight_source import list_sources
        sources = list_sources()
        sources_str = ", ".join(sources) if sources else "(无)"
        info(f"可用选品数据源: {sources_str}")
        print("  扩展: fr_cli.agent.insight_source.register_source(name, cls)")
        return False

    # ------ 历史快照 ------
    if sub == "history":
        from fr_cli.agent.insight_storage import list_history
        limit = 5
        for a in args:
            if a.isdigit():
                limit = int(a)
                break
        entries = list_history(limit=limit)
        if not entries:
            warning("暂无历史快照")
            return False
        info(f"最近 {len(entries)} 条历史快照:")
        for i, e in enumerate(entries, 1):
            print(f"  {i}. {e.get('created_at', '?')} | {e.get('source_name', '?')} | {e.get('record_count', '?')}条 | {e.get('summary', '')}")
        print("\n  查看某条: /insight show <序号>  (TODO)")
        return False

    # ------ 显示最新 ------
    if sub == "show":
        arg1 = parts[2] if len(parts) > 2 else ""
        if arg1.isdigit():
            from fr_cli.agent.insight_storage import list_history, load_history
            entries = list_history(limit=50)
            idx = int(arg1) - 1
            if 0 <= idx < len(entries):
                payload = load_history(entries[idx]["history_path"])
                _print_insights(payload, state)
            else:
                failure("序号越界")
            return False
        from fr_cli.agent.insight_storage import load_latest
        _print_insights(load_latest(), state)
        return False

    # ------ 立即提炼 ------
    if sub in ("extract", "run"):
        return _do_extract(state, args)

    # ------ 未知子命令 ------
    failure(f"未知子命令: {sub}", suggestion="用法: /insight [show|extract|history|sources]")
    return False


def _do_extract(state, args):
    """执行一次提炼,支持 --source / --path / --since / --batch"""
    # 简单参数解析
    source_name = None
    source_path = None
    since = None
    batch_size = 30
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--source" and i + 1 < len(args):
            source_name = args[i + 1]
            i += 2
        elif a == "--path" and i + 1 < len(args):
            source_path = args[i + 1]
            i += 2
        elif a == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        elif a == "--batch" and i + 1 < len(args):
            try:
                batch_size = int(args[i + 1])
            except ValueError:
                warning("--batch 参数无效,使用默认 30")
            i += 2
        else:
            warning(f"忽略未知参数: {a}")
            i += 1

    # 构建 source
    from fr_cli.agent.insight_source import (
        get_source,
        get_default_source,
    )
    source = None
    if source_path:
        if not source_name:
            # 推断: .json / .csv
            if source_path.lower().endswith(".json"):
                source_name = "json"
            elif source_path.lower().endswith(".csv"):
                source_name = "csv"
            else:
                failure("无法从路径推断数据源类型", suggestion="请加 --source json|csv")
                return False
        try:
            source = get_source(source_name, path=source_path)
        except ValueError as e:
            failure(str(e))
            return False
    elif source_name:
        try:
            source = get_source(source_name)
        except ValueError as e:
            failure(str(e))
            return False
    else:
        source = get_default_source()

    info("启动选品洞察提炼...")
    kv_block([
        ("数据源", f"{getattr(source, 'name', '?')}" + (f"({source_path})" if source_path else "")),
        ("since", since or "(全部)"),
        ("batch", str(batch_size)),
        ("模型", getattr(state, "display_model", "?")),
    ])
    print()

    try:
        from fr_cli.agent.insight_extractor import InsightExtractor
        from fr_cli.ui.spinner import Spinner
        from fr_cli.core.errors import friendly_print, is_debug
        extractor = InsightExtractor(
            client=getattr(state, "client", None),
            model_name=getattr(state, "model_name", None),
            lang=getattr(state, "lang", "zh"),
            source=source,
            batch_size=batch_size,
        )
        # Spinner 在后台跑,on_progress 回调更新显示消息
        sp = Spinner("提炼中...")
        with sp:
            def _on_progress(stage, current, total, info):
                if stage == "summarize":
                    sp.update(f"{info}...")
                elif stage == "aggregate":
                    sp.update("跨批聚合中...")
                elif stage == "save":
                    sp.update("保存到磁盘...")
                # load 阶段不显示(太快)
            result = extractor.extract(since=since, on_progress=_on_progress)
    except Exception as e:
        print(friendly_print(e, debug=is_debug()))
        return False

    if result.get("skipped"):
        reason = result.get("reason", "?")
        warning(f"跳过: {reason}")
        return False

    success("提炼完成")
    kv_block([
        ("记录数", str(result.get("record_count"))),
        ("批次数", str(result.get("batch_count"))),
        ("数据源", str(result.get("source_name"))),
    ])
    print()
    _print_insights({
        "created_at": result.get("saved_at") or "",
        "source_name": result.get("source_name"),
        "record_count": result.get("record_count"),
        "insights": result.get("insights"),
    }, state)
    print()
    info("提示: 下次 MasterAgent 启动时,这份洞察会自动注入到 system prompt")
    return False


# 别名: /insight_extract 直接 = /insight extract
def _cmd_insight_extract(state, parts):
    parts = [parts[0], "extract"] + list(parts[1:])
    return _cmd_insight(state, parts)
