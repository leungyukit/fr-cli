#!/usr/bin/env python3
"""录制工具 —— 把一次 LLM 交互录成 fixture，回放时零网络。

两种模式：

* ``--scripted``（默认，**离线**）—— 用预置脚本跑一遍并录成 fixture。
  用来生成/刷新仓库里的样例 fixture，全程不联网。
* ``--live`` —— 用**真实** provider 跑一遍并录成 fixture。
  需要本机已配置 API Key；本仓库的 CI / eval 流程**不会**调用它。

用法::

    # 生成样例 fixture（离线）
    .venv/bin/python tests/evals/record.py --out tests/evals/fixtures/sample_session.json

    # 录一次真实交互（需要已配置 provider）
    .venv/bin/python tests/evals/record.py --live --out my_session.json "帮我写个文件"

回放::

    from fr_cli.core.llm.mock import ScriptedMockClient
    client = ScriptedMockClient.load_fixture("tests/evals/fixtures/sample_session.json")
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

_EVAL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_DIR.parents[1]
for _p in (str(_EVAL_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fr_cli.core.llm.mock import (  # noqa: E402  (路径引导必须在 import 之前)
    RecordingClient,
    ScriptedMockClient,
)

#: 样例会话的脚本（离线录制用）—— 覆盖"多轮 + 工具调用"两种形态
SAMPLE_SCRIPT = [
    "好的，我来把内容写进 a.txt。\n【调用：write_file({\"path\": \"a.txt\", \"content\": \"hello world\"})】",
    "已经写好了，a.txt 里现在是 hello world。",
]


def record_scripted(
    out_path,
    script: Sequence[str],
    name: str = "scripted-session",
    user_inputs: Sequence[str] | None = None,
) -> Path:
    """离线录制：跑一遍脚本并落盘成 fixture。

    Args:
        out_path: fixture 输出路径
        script: 每轮返回的模型文本
        name: 会话名
        user_inputs: 每轮的用户输入（默认自动生成）

    Returns:
        Path: 写入的 fixture 路径
    """
    inputs = list(user_inputs) if user_inputs else [
        f"第 {i + 1} 轮输入" for i in range(len(script))
    ]
    inner = ScriptedMockClient(script=list(script))
    recorder = RecordingClient(inner, name=name)
    for user_input in inputs:
        messages = [{"role": "user", "content": user_input}]
        for _chunk in recorder.stream_chat("mock-script", messages):
            pass
    return recorder.save_fixture(out_path)


def record_live(
    out_path,
    user_inputs: Sequence[str],
    name: str = "live-session",
    provider: str | None = None,
    model: str | None = None,
) -> Path:
    """录一次真实交互（需要已配置 provider / API Key）。

    Raises:
        RuntimeError: 没有可用 provider（未配置 API Key）
    """
    from fr_cli.core.llm import create_llm_client_for
    from fr_cli.conf.config import load_config

    cfg = load_config()
    client, resolved_provider, resolved_model = create_llm_client_for(
        provider or "", model or "", cfg
    )
    if client is None or getattr(client, "is_mock", False):
        raise RuntimeError(
            "没有可用的真实 provider（未配置 API Key）—— 离线录制请用 --scripted"
        )
    recorder = RecordingClient(client, name=name)
    for user_input in user_inputs:
        messages = [{"role": "user", "content": user_input}]
        for _chunk in recorder.stream_chat(
            resolved_model or "unknown", messages
        ):
            pass
    return recorder.save_fixture(out_path)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="把一次 LLM 交互录成 fixture")
    parser.add_argument(
        "--out",
        default=str(_EVAL_DIR / "fixtures" / "sample_session.json"),
        help="fixture 输出路径",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="录一次真实交互（需要 API Key；默认是离线脚本录制）",
    )
    parser.add_argument(
        "--name", default="scripted-session", help="会话名（写进 fixture 备注）"
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="--live 模式下的用户输入（可多条）",
    )
    args = parser.parse_args(argv)

    if args.live:
        if not args.inputs:
            print("[错误] --live 模式需要至少一条用户输入", file=sys.stderr)
            return 2
        path = record_live(args.out, args.inputs, name=args.name)
    else:
        path = record_scripted(args.out, SAMPLE_SCRIPT, name=args.name)
    print(f"[OK] fixture 已写入: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
