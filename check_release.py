#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前自检：扫描构建产物（wheel / sdist）里的敏感文件与密钥形状内容。

用法::

    python check_release.py <目录或文件> [更多...] [--strict]

目标是在 ``twine upload`` 之前挡住两类事故：

1. **把用户配置或密钥打进包**：例如 ``~/.fr_cli/config.json``、``.env``、
   ``id_rsa``、``.pypirc`` 之类只该留在本机的东西。
2. **源码里硬编码密钥**：OpenAI / Anthropic / GitHub / Slack / PyPI 等常见
   令牌形状，以及 ``api_key = "..."`` 这类带引号字面量的赋值。

判定规则
--------
* 命中**文件名黑名单**或**内容密钥形状** -> ERROR，退出码 1。
* 只命中**卫生问题**（``.DS_Store``、``__pycache__``、sdist 缺 CHANGELOG 等）
  -> WARNING，退出码仍为 0；加 ``--strict`` 才让 WARNING 也失败。

实现上的几个规避误报的决定
--------------------------
* 只扫文本文件：二进制（图片等）以及前 8KB 含 NUL 字节的文件直接跳过。
* 跳过 ``*.dist-info/RECORD``：里面全是 base64 哈希，属正常内容。
* 单文件超过 ``MAX_BYTES`` 跳过，避免拖慢扫描。
* 通用键值正则**要求值是引号字面量**，所以 ``token = secrets.token_urlsafe(16)``
  这种从函数/变量取值的写法不会误报（fr-cli 自己的 server.py 就是这么写的）。
* 启发式规则在 ``tests/`` 下降为 WARNING：测试固件里故意放假地址、假包名、
  假 marker 是常态，但真漏了密钥也仍会提示。
* 确认是误报时，在那一行写上 ``# release-check: ignore`` 即可整行豁免。
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
import tarfile
import zipfile

MAX_BYTES = 1024 * 1024

# --------------------------------------------------------------- 文件名黑名单
# 精确匹配 basename
_BANNED_EXACT = {
    ".env", ".pypirc", ".netrc", ".npmrc", ".git-credentials",
    "config.json", "credentials", "id_rsa", "id_dsa", "id_ecdsa",
    "id_ed25519", ".fr_cli", "settings.local.json",
}
# 匹配 basename 后缀
_BANNED_SUFFIX = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk", ".crt")
# fnmatch 风格
_BANNED_GLOB = (
    ".env.*", "*.pypirc", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "*credential*", "*secret*", "*.p8", "*.asc",
)
# 匹配完整路径片段
_BANNED_PATH_FRAGMENT = ("/.fr_cli/", "/secrets/", "/credentials/", "/.ssh/")

# --------------------------------------------------------------- 内容密钥形状
_SECRET_PATTERNS = (
    ("OpenAI/Anthropic sk- 密钥", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("Anthropic sk-ant- 密钥", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub Token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("GitLab PAT", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("Google API Key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Google OAuth Refresh", re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}\b")),
    ("PyPI Token", re.compile(r"\bpypi-[A-Za-z0-9_\-]{16,}\b")),
    ("npm Token", re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b")),
    ("私钥 PEM 头", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
)

# 带引号字面量的敏感键赋值：值是 >=20 的引号串才算，避开"从变量/函数取值"的误报
_ASSIGN_RE = re.compile(
    r"""(?ix)
    \b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|refresh[_-]?token|
        secret[_-]?key|client[_-]?secret|password|passwd|private[_-]?key)\b
    \s*[:=]\s*
    ["']([A-Za-z0-9_\-+/=.]{20,})["']
    """
)

# 引号包住的长随机串（疑似硬编码密钥）。同时要求引号、长度和字符多样性，
# 所以 snake_case 标识符、===== 分隔线、URL、中文文案都不会命中。
_RANDOM_LITERAL_RE = re.compile(r"""["']([A-Za-z0-9+/=_-]{32,})["']""")


def _looks_random(s):
    """判断一串字符是否像随机令牌：够长、字符够杂、大小写字母和数字都有。

    要求大小写混含是关键——真人写的假数据（``this-package-does-not-exist-xyz-12345``、
    ``fr-cli-gatekeeper-manager-test-4712``）几乎全是小写加数字，而 base64/hex
    令牌天然大小写混合。
    """
    if len(s) < 32 or len(set(s)) < 12:
        return False
    return (
        any(c.isupper() for c in s)
        and any(c.islower() for c in s)
        and any(c.isdigit() for c in s)
    )


# 行内豁免：在这一行写上 release-check: ignore 就不再报它
_SUPPRESS_RE = re.compile(r"release-check\s*:\s*ignore")


def _is_test_path(path):
    """是否位于 tests/ 下。测试固件里全是故意的假随机数据。"""
    norm = "/" + path.replace(os.sep, "/")
    return "/tests/" in norm or norm.startswith("/tests/")


class Finding(object):
    """一条审计结果。level 为 ERROR 或 WARNING。"""

    __slots__ = ("level", "path", "lineno", "kind", "detail")

    def __init__(self, level, path, lineno, kind, detail=""):
        self.level = level
        self.path = path
        self.lineno = lineno
        self.kind = kind
        self.detail = detail

    def __str__(self):
        loc = self.path if not self.lineno else "%s:%d" % (self.path, self.lineno)
        tail = (" | " + self.detail) if self.detail else ""
        return "[%s] %s - %s%s" % (self.level, loc, self.kind, tail)


def _mask(s):
    """脱敏：只留前 6 个字符和长度，避免把密钥原文抄进日志。"""
    s = s.strip()
    if len(s) <= 10:
        return "%s (%d chars)" % (s, len(s))
    return "%s... (%d chars)" % (s[:6], len(s))


def check_member_name(path):
    """文件名/路径检查。返回 (level, kind) 或 None。"""
    base = os.path.basename(path).lower()
    if base in _BANNED_EXACT:
        return ("ERROR", "文件名命中黑名单：只该留在本机的配置/密钥文件")
    if base.endswith(_BANNED_SUFFIX):
        return ("ERROR", "文件名后缀命中黑名单：证书/私钥/密钥库")
    for pat in _BANNED_GLOB:
        if fnmatch.fnmatch(base, pat):
            return ("ERROR", "文件名匹配黑名单模式 %s" % pat)
    norm = "/" + path.replace(os.sep, "/")
    for frag in _BANNED_PATH_FRAGMENT:
        if frag in norm:
            return ("ERROR", "路径包含敏感目录片段 %s" % frag)
    return None


def check_member_hygiene(path):
    """卫生问题检查（WARNING 级）。"""
    base = os.path.basename(path)
    norm = "/" + path.replace(os.sep, "/")
    if base == ".DS_Store":
        return ("WARNING", "macOS 垃圾文件 .DS_Store 不应进产物")
    if "__pycache__" in norm or base.endswith((".pyc", ".pyo")):
        return ("WARNING", "字节码缓存不应进产物")
    return None


def scan_text(path, raw):
    """对单个文本成员逐行做密钥形状扫描，每行最多报一条。

    * 明确形状（sk-、AKIA、PEM 头等）一律 ERROR，tests/ 里也不例外。
    * 启发式（引号赋值、长随机串）在 tests/ 下降为 WARNING——测试固件里
      故意放假地址/假包名/假 marker 是常态，但真漏了密钥也仍会提示。
    * 行内出现 ``release-check: ignore`` 则整行豁免。
    """
    findings = []
    text = raw.decode("utf-8", "replace")
    heur_level = "WARNING" if _is_test_path(path) else "ERROR"
    for lineno, line in enumerate(text.splitlines(), 1):
        if _SUPPRESS_RE.search(line):
            continue
        for kind, rx in _SECRET_PATTERNS:
            m = rx.search(line)
            if m:
                findings.append(Finding("ERROR", path, lineno, kind, _mask(m.group(0))))
                break
        else:
            m = _ASSIGN_RE.search(line)
            if m:
                findings.append(
                    Finding(heur_level, path, lineno, "敏感键赋值为引号字面量", _mask(m.group(1)))
                )
                continue
            for m in _RANDOM_LITERAL_RE.finditer(line):
                if _looks_random(m.group(1)):
                    findings.append(
                        Finding(heur_level, path, lineno, "引号内长随机串（疑似硬编码密钥）", _mask(m.group(1)))
                    )
                    break
    return findings


def iter_members(artifact):
    """逐个产出 (路径, 原始字节)。支持 wheel(zip) 与 sdist(tar.gz)。"""
    if zipfile.is_zipfile(artifact):
        with zipfile.ZipFile(artifact) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                yield info.filename, zf.read(info)
    elif tarfile.is_tarfile(artifact):
        with tarfile.open(artifact) as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                fh = tf.extractfile(m)
                if fh is None:
                    continue
                yield m.name, fh.read()
    else:
        raise ValueError("无法识别的产物格式（既不是 zip 也不是 tar）: %s" % artifact)


def _skip_by_name(path):
    """内容扫描前的名字级跳过：这些文件天生就是长哈希/元数据。"""
    return path.replace(os.sep, "/").endswith(".dist-info/RECORD")


def audit_artifact(artifact):
    """审计单个产物，返回 (findings, 成员名列表)。"""
    findings = []
    names = []
    for path, raw in iter_members(artifact):
        names.append(path)
        hit = check_member_name(path)
        if hit:
            findings.append(Finding(hit[0], path, 0, hit[1]))
            continue
        hit = check_member_hygiene(path)
        if hit:
            findings.append(Finding(hit[0], path, 0, hit[1]))
            continue
        if _skip_by_name(path) or len(raw) > MAX_BYTES:
            continue
        if b"\x00" in raw[:8192]:
            continue
        findings.extend(scan_text(path, raw))
    findings.extend(audit_hygiene(artifact, names))
    return findings, names


def audit_hygiene(artifact, names):
    """产物整体的卫生检查（WARNING 级）。"""
    out = []
    norm = artifact.replace(os.sep, "/").lower()
    is_sdist = norm.endswith((".tar.gz", ".tgz"))
    bases = set(os.path.basename(n) for n in names)
    if is_sdist:
        if "CHANGELOG.md" not in bases:
            out.append(Finding(
                "WARNING", artifact, 0, "sdist 未包含 CHANGELOG.md（MANIFEST.in 未列）"
            ))
    else:
        if any(n.startswith("tests/") or "/tests/" in n.replace(os.sep, "/") for n in names):
            out.append(Finding("WARNING", artifact, 0, "wheel 中包含 tests/ 目录"))
    return out


def collect_targets(paths):
    """把传入的文件/目录展开成具体产物文件列表。"""
    targets = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                full = os.path.join(p, name)
                if os.path.isfile(full) and name.endswith((".whl", ".tar.gz", ".tgz")):
                    targets.append(full)
        else:
            targets.append(p)
    return targets


def run_audit(paths, strict=False):
    """执行审计并打印报告，返回进程退出码。"""
    targets = collect_targets(paths)
    if not targets:
        sys.stderr.write("未找到可审计的产物（.whl / .tar.gz）\n")
        return 1
    all_findings = []
    for t in targets:
        findings, names = audit_artifact(t)
        all_findings.extend(findings)
        errs = [f for f in findings if f.level == "ERROR"]
        warns = [f for f in findings if f.level == "WARNING"]
        print("== %s（%d 成员，%d ERROR / %d WARNING）" % (t, len(names), len(errs), len(warns)))
        for f in findings:
            print("   " + str(f))
    total_err = sum(1 for f in all_findings if f.level == "ERROR")
    total_warn = sum(1 for f in all_findings if f.level == "WARNING")
    print("--")
    print("合计：%d ERROR，%d WARNING" % (total_err, total_warn))
    if total_err:
        print("结论：未通过 —— 发布前必须处理上面的 ERROR。")
        return 1
    if total_warn and strict:
        print("结论：未通过（--strict 下 WARNING 也算失败）。")
        return 1
    print("结论：通过 —— 未发现敏感文件或密钥形状内容。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="发布前自检：扫描 wheel/sdist 里的敏感文件与密钥形状内容"
    )
    ap.add_argument("paths", nargs="+", help="产物文件，或包含产物的目录")
    ap.add_argument("--strict", action="store_true", help="让 WARNING 也导致失败")
    args = ap.parse_args(argv)
    return run_audit(args.paths, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
