"""ANSI 转义序列的还原 / 渲染 / 剥离

场景:
- PTY 捕获、日志文件、复制粘贴到不支持 ESC 的查看器时, ESC(0x1B) 被
  显示端丢弃或替换成 `?`, 原始序列就变成可见垃圾:
  `?[96m?[1m•?[0m` 本该是一个"亮青加粗的项目符号"。
- render_ansi(): 把残损序列还原成真 ESC 序列后写终端, 让终端重新解释
  → 颜色 / 加粗 / 项目符号恢复显示。
- strip_ansi(): 非 TTY(管道 / 重定向 / 落日志)场景剥掉所有序列,
  只保留可见文本(项目符号 • 等原样保留)。

CLI:
    cat screen.txt | python -m fr_cli.ui.ansi        # TTY: 恢复颜色
    python -m fr_cli.ui.ansi screen.txt > clean.txt   # 非 TTY: 干净纯文本
"""
import re
import sys

# 真实 ESC 序列(任意 CSI 终结字母)
_REAL_SEQ_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# 残损序列: ESC 被吃掉后只剩 `?[96m`。只认 `m` 结尾 + 纯数字参数,
# 且参数必须在已知 SGR 码集合内, 避免把正常文本里的 `?[3` 当成序列。
_DAMAGED_SEQ_RE = re.compile(r"\?\[([0-9;]+)m")

# 已知 SGR(Select Graphic Rendition)参数码
_SGR_SIMPLE = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
    21, 22, 23, 24, 25, 27, 28, 29,
    53, 55,
}
# 30-37 / 40-47 / 90-97 / 100-107 前景背景(含亮色)
_SGR_SIMPLE |= set(range(30, 38)) | set(range(40, 48))
_SGR_SIMPLE |= set(range(90, 98)) | set(range(100, 108))


def _is_known_sgr(params: str) -> bool:
    """判断分号参数串是否是已知 SGR 码(支持 38;5;n / 48;5;n / 38;2;r;g;b)"""
    parts = params.split(";")
    if not parts or not all(p.isdigit() for p in parts):
        return False
    if len(parts) == 1:
        return int(parts[0]) in _SGR_SIMPLE
    # 256 色 / 真彩色扩展
    if parts[0] in ("38", "48") and len(parts) >= 3:
        if parts[1] == "5" and len(parts) == 3:
            return 0 <= int(parts[2]) <= 255
        if parts[1] == "2" and len(parts) == 5:
            return all(0 <= int(p) <= 255 for p in parts[2:])
    return False


def has_ansi(text: str) -> bool:
    """文本中是否含 ANSI 序列(真实 ESC 或残损 `?[..m` 形)"""
    if _REAL_SEQ_RE.search(text):
        return True
    return any(_is_known_sgr(m.group(1)) for m in _DAMAGED_SEQ_RE.finditer(text))


def normalize_ansi(text: str) -> str:
    """把残损 `?[96m` 还原成真 `\\x1b[96m`; 真序列原样返回。

    保守策略: 只有参数是已知 SGR 码的 `?[..m` 才还原, 正常文本里的
    问号(如 `选 A?[1]` 这种)不受影响。
    """
    def _sub(m: "re.Match") -> str:
        return f"\x1b[{m.group(1)}m" if _is_known_sgr(m.group(1)) else m.group(0)

    return _DAMAGED_SEQ_RE.sub(_sub, text)


def strip_ansi(text: str) -> str:
    """剥掉所有 ANSI 序列(真实 + 残损), 只留可见文本"""
    text = _REAL_SEQ_RE.sub("", text)
    text = _DAMAGED_SEQ_RE.sub(lambda m: "" if _is_known_sgr(m.group(1)) else m.group(0), text)
    return text


def render_ansi(text: str, file=None) -> None:
    """把文本里的序列(含残损形)还原后写入目标流, 让终端解释出颜色/加粗。

    :param file: 目标流; 默认 sys.stdout。若 fr-cli REPL 内 prompt_toolkit
                 patch_stdout 代理导致序列显示异常, 可传 sys.__stdout__
                 绕过代理直写真实终端。
    """
    out = file if file is not None else sys.stdout
    out.write(normalize_ansi(text))
    try:
        out.flush()
    except Exception:
        pass


def main(argv=None) -> int:
    """CLI 入口: 读文件或 stdin, 按目标是否 TTY 分流渲染"""
    argv = list(sys.argv[1:] if argv is None else argv)
    chunks = []
    if argv:
        for path in argv:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                chunks.append(f.read())
    else:
        chunks.append(sys.stdin.read())
    text = "".join(chunks)

    if sys.stdout.isatty():
        # 真终端: 还原序列, 让终端解释出颜色/加粗/项目符号
        render_ansi(text)
    else:
        # 管道/重定向: 输出干净纯文本, 不泄漏任何转义序列
        sys.stdout.write(strip_ansi(text))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
