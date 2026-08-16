"""
竞品监控能力缺口扫描命令
/competitor_gaps

用法:
  /competitor_gaps                  — 立即跑一次扫描,显示缺口报告
  /competitor_gaps scan             — 同上
  /competitor_gaps show             — 显示最近一次的报告
  /competitor_gaps add <name>       — 把指定缺口推到 /hermes review 队列(供后续自动构建)
  /competitor_gaps model            — 显示当前能力模型路径 + 概要
"""
from fr_cli.ui.output import (
    success, failure, warning, info, header, kv_block
)
from fr_cli.core.errors import friendly_print, is_debug


def _print_report(report):
    """把报告 dict 打印到终端"""
    if not report:
        warning("暂无报告", detail="先跑一次 /competitor_gaps scan")
        return
    from fr_cli.dynamic_builder.competitor_gap_scan import format_report_text
    text = format_report_text(report)
    print(text)


def _cmd_competitor_gaps(state, parts):
    sub = parts[1].lower() if len(parts) > 1 else "scan"
    args = parts[2:]

    # ------ 显示模型 ------
    if sub == "model":
        from fr_cli.dynamic_builder.competitor_gap_scan import (
            DEFAULT_MODEL_PATH, load_model,
        )
        try:
            model = load_model()
            header("竞品监控能力模型")
            kv_block([
                ("路径", DEFAULT_MODEL_PATH),
                ("域", str(model.get("domain", "?"))),
                ("标题", str(model.get("title", "?"))),
                ("版本", str(model.get("version", "?"))),
                ("能力数", str(len(model.get("capabilities", [])))),
            ])
            print()
            info("能力清单:")
            for c in model.get("capabilities", []):
                if not isinstance(c, dict):
                    continue
                p = c.get("priority", "medium")
                print(f"  [{p:6}] {c.get('name', '?'):35} — {c.get('description', '')}")
        except Exception as e:
            print(friendly_print(e, debug=is_debug()))
        return False

    # ------ 显示最近报告 ------
    if sub == "show":
        from fr_cli.dynamic_builder.competitor_gap_scan import load_latest_report
        _print_report(load_latest_report())
        return False

    # ------ 立即扫描 ------
    if sub in ("scan", ""):
        from fr_cli.dynamic_builder.competitor_gap_scan import CompetitorGapScanner
        info("扫描竞品监控能力缺口...")
        kv_block([
            ("能力模型", "fr_cli/dynamic_builder/capabilities/competitor_monitor.yaml"),
            ("模型", getattr(state, "display_model", "?")),
        ])
        print()
        try:
            from fr_cli.ui.spinner import Spinner
            scanner = CompetitorGapScanner(state=state)
            sp = Spinner("扫描中...")
            with sp:
                def _on_progress(stage, current, total, info):
                    if stage == "analyze" and current > 0:
                        sp.update(f"{info}")
                    elif stage == "load_model":
                        sp.update(info)
                report = scanner.scan(save_report=True, on_progress=_on_progress)
        except Exception as e:
            print(friendly_print(e, debug=is_debug()))
            return False

        _print_report(report)
        gaps = report.get("gaps") or []
        if gaps:
            print()
            info("提示: /competitor_gaps add <name>  把指定缺口推到 /hermes review 队列")
            info("      /hermes review approve <id>     批准后会自动构建工具")
        return False

    # ------ 推送到 review 队列 ------
    if sub == "add":
        if not args:
            failure("缺少参数", suggestion="用法: /competitor_gaps add <capability_name>")
            return False
        target = args[0]
        from fr_cli.dynamic_builder.competitor_gap_scan import load_latest_report
        report = load_latest_report()
        if not report:
            warning("暂无报告", detail="先跑一次 /competitor_gaps scan")
            return False
        target_gap = next(
            (g for g in (report.get("gaps") or []) if g.get("name") == target),
            None,
        )
        if not target_gap:
            failure(f"未找到缺口: {target}", suggestion=f"可用缺口: {[g.get('name') for g in report.get('gaps', [])]}")
            return False

        # 推到 hermes review queue
        try:
            from fr_cli.agent.review_queue import ReviewQueue
            queue = ReviewQueue()
            item = queue.add(
                artifact_type="competitor_gap",
                code="",  # 缺口本身没有代码,只是需求描述
                suggested_name=target_gap.get("name", ""),
                metadata={
                    "capability": target_gap.get("name"),
                    "description": target_gap.get("description"),
                    "key_signals": target_gap.get("key_signals"),
                    "priority": target_gap.get("priority"),
                    "example_usage": target_gap.get("example_usage"),
                    "source": "competitor_gap_scan",
                },
            )
            success(f"已推到 /hermes review 队列: {item.id}", detail=f"后续: /hermes review approve {item.id}  批准后会触发 dynamic_build")
        except Exception as e:
            print(friendly_print(e, debug=is_debug()))
        return False

    # ------ 未知子命令 ------
    failure(f"未知子命令: {sub}", suggestion="用法: /competitor_gaps [scan|show|add <name>|model]")
    return False
