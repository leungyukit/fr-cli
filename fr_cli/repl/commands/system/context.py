"""
上下文压缩管理命令：/context compress/threshold/keep/status
"""
from fr_cli.memory.compress import estimate_tokens, maybe_compress
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET


def _cmd_context(state, parts):
    """上下文压缩管理

    用法:
      /context compress              立即压缩当前会话
      /context threshold [N]         查看/设置自动压缩阈值（0 关闭）
      /context keep [N]              查看/设置保留最近轮数
      /context status                查看当前估算 token 与配置
    """
    sub = parts[1] if len(parts) > 1 else "status"
    is_zh = state.lang == "zh"

    if sub == "compress":
        if not state.model_name:
            print(f"{RED}{'模型未配置' if is_zh else 'Model not configured'}{RESET}")
            return False
        messages = state.messages
        keep_recent = getattr(state, "context_compress_keep_recent", 5)
        before = estimate_tokens(messages)
        compressed, did_compress, _, after = maybe_compress(
            messages,
            state.client,
            state.model_name,
            lang=state.lang,
            threshold=0,  # 强制压缩
            keep_recent=keep_recent,
        )
        if did_compress:
            state.messages = compressed
            saved = max(0, before - after)
            print(f"{GREEN}✅ {'已压缩早期对话' if is_zh else 'Compressed early conversation'}{RESET}")
            print(f"   {DIM}{'估算 token' if is_zh else 'Estimated tokens'}: {before} → {after} ({'节省' if is_zh else 'saved'} {saved}){RESET}")
        else:
            print(f"{YELLOW}⚠️ {'没有可压缩的早期对话' if is_zh else 'No early conversation to compress'}{RESET}")
        return False

    if sub == "threshold":
        val = parts[2] if len(parts) > 2 else ""
        if val:
            try:
                v = int(val)
                if v < 0:
                    raise ValueError
                state.update_context_compress_threshold(v)
                print(f"{GREEN}✅ {'自动压缩阈值已设为' if is_zh else 'Auto-compress threshold set to'} {v}{RESET}")
            except ValueError:
                print(f"{RED}❌ {'阈值必须是非负整数' if is_zh else 'Threshold must be a non-negative integer'}{RESET}")
        else:
            print(f"{DIM}{'当前自动压缩阈值' if is_zh else 'Current auto-compress threshold'}: {state.context_compress_threshold}{RESET}")
        return False

    if sub == "keep":
        val = parts[2] if len(parts) > 2 else ""
        if val:
            try:
                v = int(val)
                if v < 1:
                    raise ValueError
                state.update_context_compress_keep_recent(v)
                print(f"{GREEN}✅ {'保留最近轮数已设为' if is_zh else 'Keep-recent rounds set to'} {v}{RESET}")
            except ValueError:
                print(f"{RED}❌ {'保留轮数必须是正整数' if is_zh else 'Keep-recent must be a positive integer'}{RESET}")
        else:
            print(f"{DIM}{'当前保留最近轮数' if is_zh else 'Current keep-recent rounds'}: {state.context_compress_keep_recent}{RESET}")
        return False

    # status
    before = estimate_tokens(state.messages)
    print(f"{CYAN}{'上下文压缩状态' if is_zh else 'Context compression status'}{RESET}")
    print(f"  {'自动压缩阈值' if is_zh else 'Auto threshold'}: {state.context_compress_threshold}")
    print(f"  {'保留最近轮数' if is_zh else 'Keep recent rounds'}: {state.context_compress_keep_recent}")
    print(f"  {'当前会话估算 token' if is_zh else 'Current estimated tokens'}: {before}")
    return False
