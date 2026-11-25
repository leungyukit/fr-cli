"""
轻量代码语法高亮 —— 零依赖（只用标准库 + ANSI 转义）

为什么需要
----------
流式 Markdown 渲染器（``fr_cli/ui/markdown_stream.py``）此前把代码块内容
整行染成 DIM 灰：关键字、字符串、注释、数字全是同一个颜色，代码读起来
像一团糊。仓库里其实早有关键字表（``core/optimizations.py::LANG_KEYWORDS``），
但**从未被任何地方引用** —— 规划过、没实现。

设计约束
--------
* **不引入新运行时依赖**（项目明确约束）。不用 pygments，纯 Python 实现。
* 关色时必须**原样返回** —— 不能拼出任何转义序列（非 TTY / NO_COLOR /
  prompt_toolkit.patch_stdout 代理期都会把 ESC 显示成 ``?[96m`` 乱码）。
* 逐行高亮，不做跨行状态（字符串跨行、块注释都按普通行处理）——
  流式渲染器本来也是逐行喂进来的，跨行状态反而容易和折叠逻辑打架。

颜色约定
--------
===========  ========
token        颜色
===========  ========
关键字        MAGENTA
字符串        GREEN
注释          DIM
数字          YELLOW
===========  ========
"""
from typing import Dict, Optional, Set

from fr_cli.ui.ui import DIM, GREEN, MAGENTA, RESET, YELLOW


# 各语言的关键字表
# （原 core/optimizations.py::LANG_KEYWORDS —— 那边是死代码，这里是它的实现）
KEYWORDS: Dict[str, Set[str]] = {
    "python": {
        "def", "class", "import", "from", "return", "if", "else", "elif",
        "for", "while", "try", "except", "finally", "with", "as", "in", "is",
        "not", "and", "or", "None", "True", "False", "self", "lambda", "yield",
        "async", "await", "pass", "break", "continue", "raise", "global",
        "nonlocal", "assert", "del", "match", "case",
    },
    "javascript": {
        "function", "const", "let", "var", "return", "if", "else", "for",
        "while", "class", "extends", "new", "this", "import", "export", "from",
        "default", "async", "await", "try", "catch", "finally", "throw",
        "typeof", "instanceof", "switch", "case", "break", "continue", "delete",
        "in", "of", "null", "undefined", "true", "false",
    },
    "bash": {
        "if", "then", "else", "elif", "fi", "for", "do", "done", "while",
        "case", "esac", "function", "echo", "export", "local", "return",
        "source", "alias", "unset", "shift", "trap",
    },
    "go": {
        "func", "var", "const", "if", "else", "for", "range", "return",
        "package", "import", "type", "struct", "interface", "map", "chan",
        "go", "defer", "select", "switch", "case", "break", "continue",
        "fallthrough", "nil", "true", "false",
    },
    "rust": {
        "fn", "let", "mut", "if", "else", "for", "while", "loop", "match",
        "return", "struct", "enum", "trait", "impl", "pub", "use", "mod", "as",
        "where", "ref", "move", "dyn", "crate", "self", "Self", "true",
        "false", "unsafe", "async", "await",
    },
}


# 语言别名 → 规范名（代码块围栏里写什么都有可能）
LANG_ALIASES: Dict[str, str] = {
    "py": "python", "python3": "python", "py3": "python",
    "js": "javascript", "jsx": "javascript", "ts": "javascript",
    "typescript": "javascript", "tsx": "javascript", "node": "javascript",
    "sh": "bash", "shell": "bash", "zsh": "bash", "console": "bash",
    "golang": "go",
    "rs": "rust",
}


# 各语言的行注释符号
_COMMENT_TOKENS: Dict[str, str] = {
    "python": "#",
    "bash": "#",
    "javascript": "//",
    "go": "//",
    "rust": "//",
}


def normalize_lang(lang: str) -> Optional[str]:
    """把围栏上的语言标识归一化到规范名；不支持的语言返回 None。

    Args:
        lang: 代码块围栏里的语言标识（可能是 ``py`` / ``Python`` / ``''``）

    Returns:
        str | None: 规范语言名；无法识别时返回 None
    """
    if not lang:
        return None
    key = lang.strip().lower()
    key = LANG_ALIASES.get(key, key)
    return key if key in KEYWORDS else None


def _color(text: str, code: str) -> str:
    """给一段文本着色（调用方已保证颜色可用）"""
    if not text or not code:
        return text
    return f"{code}{text}{RESET}"


def highlight_code(line: str, lang: str, use_color: bool = True) -> str:
    """对一行代码做语法高亮。

    Args:
        line: 代码行（单行，不含换行符）
        lang: 语言标识（见 :func:`normalize_lang`）
        use_color: 是否着色。False 时**原样返回**（不拼任何转义序列）

    Returns:
        str: 高亮后的代码行
    """
    if not use_color or not line:
        return line

    norm = normalize_lang(lang)
    if norm is None:
        return line

    keywords = KEYWORDS[norm]
    comment_token = _COMMENT_TOKENS.get(norm, "")

    out = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]

        # 注释：行注释符号之后的全部内容
        if comment_token and line.startswith(comment_token, i):
            out.append(_color(line[i:], DIM))
            break

        # 字符串：单引号 / 双引号，支持反斜杠转义
        if ch in ("'", '"'):
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == ch:
                    j += 1
                    break
                j += 1
            out.append(_color(line[i:j], GREEN))
            i = j
            continue

        # 标识符 / 关键字
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            out.append(_color(word, MAGENTA) if word in keywords else word)
            i = j
            continue

        # 数字（含小数 / 下划线分隔）
        if ch.isdigit():
            j = i
            while j < n and (line[j].isalnum() or line[j] in "._"):
                j += 1
            out.append(_color(line[i:j], YELLOW))
            i = j
            continue

        out.append(ch)
        i += 1

    return "".join(out)
