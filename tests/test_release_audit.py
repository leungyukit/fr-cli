# -*- coding: utf-8 -*-
"""check_release.py 发布前自检的单测。

覆盖三类行为：
1. **能抓住**：黑名单文件名、各类密钥形状、引号内的长随机串。
2. **不误报**：snake_case 标识符、===== 分隔线、URL、二进制、RECORD 哈希、
   从函数/变量取值的 token 赋值。
3. **降级与豁免**：tests/ 下的启发式命中降为 WARNING，行内
   ``release-check: ignore`` 整行豁免。
"""

import io
import os
import sys
import tarfile
import zipfile

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import check_release  # noqa: E402

CLEAN_PY = "x = 1\nprint('hello')\n"
METADATA = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"


def _build_wheel(path, files):
    with zipfile.ZipFile(str(path), "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data.encode("utf-8") if isinstance(data, str) else data)
    return str(path)


def _build_sdist(path, files, prefix="demo-1.0"):
    with tarfile.open(str(path), "w:gz") as tf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            info = tarfile.TarInfo("%s/%s" % (prefix, name))
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return str(path)


def _audit(files, suffix=".whl", builder=None):
    """把 files 打包成产物并审计，返回 findings 列表。"""
    import tempfile

    tmp = tempfile.mkdtemp(prefix="fr_relaudit_")
    art = os.path.join(tmp, "demo-1.0" + suffix)
    (builder or _build_wheel)(art, files)
    findings, _names = check_release.audit_artifact(art)
    return findings


def _kinds(findings):
    return [f.kind for f in findings]


def _levels(findings):
    return set(f.level for f in findings)


# ------------------------------------------------------------------ 能抓住
def test_banned_filename_config_json():
    fs = _audit({"pkg/config.json": '{"api_key": "x"}'})
    assert len(fs) == 1 and fs[0].level == "ERROR"


def test_banned_filename_dotenv():
    fs = _audit({"pkg/.env": "OPENAI_API_KEY=abc\n"})
    assert len(fs) == 1 and fs[0].level == "ERROR"


def test_banned_filename_private_key():
    fs = _audit({"pkg/id_rsa": "not a real key\n"})
    assert len(fs) == 1 and fs[0].level == "ERROR"


def test_banned_suffix_pem():
    fs = _audit({"pkg/cert.pem": "x\n"})
    assert len(fs) == 1 and fs[0].level == "ERROR"


@pytest.mark.parametrize("line,kind", [
    ('K = "sk-abcdefghijklmnopqrstuvwxyz012345"\n', "OpenAI/Anthropic sk- 密钥"),
    ('K = "AKIAIOSFODNN7EXAMPLE"\n', "AWS Access Key"),
    ('K = "ghp_1234567890abcdefghijklmnopqrstuvwxyzABCD"\n', "GitHub Token"),
    ('K = "xoxb-1234567890-abcdefghijkl"\n', "Slack Token"),
    ('K = "-----BEGIN RSA PRIVATE KEY-----"\n', "私钥 PEM 头"),
])
def test_secret_patterns_caught(line, kind):
    fs = _audit({"pkg/creds.py": line})
    assert len(fs) == 1, _kinds(fs)
    assert fs[0].kind == kind
    assert fs[0].level == "ERROR"


def test_quoted_assign_literal_flagged():
    fs = _audit({"pkg/a.py": 'api_key = "aB3xY9zQ7wLmN2pR5tK8jH4"\n'})
    assert len(fs) == 1 and fs[0].kind == "敏感键赋值为引号字面量"


def test_long_random_literal_flagged_outside_tests():
    fs = _audit({"pkg/a.py": 'TOKEN = "aB3xY9zQ7wLmN2pR5tK8jH4gT6vD1sW0"\n'})
    assert len(fs) == 1, _kinds(fs)
    assert fs[0].level == "ERROR"
    assert fs[0].kind == "引号内长随机串（疑似硬编码密钥）"


# ------------------------------------------------------------------ 不误报
def test_clean_wheel_no_findings():
    fs = _audit({
        "pkg/__init__.py": CLEAN_PY,
        "pkg-1.0.dist-info/METADATA": METADATA,
        "pkg/conf/default_models.yaml": 'zhipu:\n  env_key: ZHIPU_API_KEY\n',
    })
    assert fs == [], _kinds(fs)


@pytest.mark.parametrize("line", [
    "self._token = secrets.token_urlsafe(16)\n",
    "self.api_key = self.client.api_key\n",
    "def test_competitor_gap_scan_handles_missing_config_file():\n",
    "# " + "=" * 70 + "\n",
    "# " + "-" * 70 + "\n",
    'BASE = "https://open.bigmodel.cn/api/coding/paas/v4"\n',
    "MODEL = \"glm-4-flash\"\n",
    "MSG = \"凡人打字机 - 自进化多模型终端 Agent\"\n",
    "assert is_installed(\"this-package-does-not-exist-xyz-12345\") is False\n",
])
def test_no_false_positive(line):
    assert _audit({"pkg/a.py": line}) == []


def test_binary_file_skipped():
    blob = b"\xff\xd8\xff\xe0" + b"sk-abcdefghijklmnopqrstuvwxyz012345" + b"\x00" * 64
    assert _audit({"pkg/splash.jpeg": blob}) == []


def test_dist_info_record_skipped():
    rec = "pkg/a.py,sha256=" + "a1b2c3d4e5" * 6 + ",123\n"
    assert _audit({"pkg-1.0.dist-info/RECORD": rec}) == []


def test_oversized_file_skipped():
    big = "x" * (check_release.MAX_BYTES + 10) + 'sk-abcdefghijklmnopqrstuvwxyz012345'
    assert _audit({"pkg/big.txt": big}) == []


# ------------------------------------------------------- 降级与豁免
def test_tests_dir_heuristic_demoted_to_warning():
    """同一行启发式命中，在 tests/ 下是 WARNING，在包内是 ERROR。"""
    line = 'MARKER = "aB3xY9zQ7wLmN2pR5tK8jH4gT6vD1sW0"\n'
    fs = _audit({"tests/test_x.py": line})
    heur = [f for f in fs if f.kind == "引号内长随机串（疑似硬编码密钥）"]
    assert len(heur) == 1 and heur[0].level == "WARNING"

    fs2 = _audit({"pkg/a.py": line})
    heur2 = [f for f in fs2 if f.kind == "引号内长随机串（疑似硬编码密钥）"]
    assert len(heur2) == 1 and heur2[0].level == "ERROR"


def test_tests_dir_explicit_secret_still_error():
    line = 'K = "sk-abcdefghijklmnopqrstuvwxyz012345"\n'
    fs = _audit({"tests/test_x.py": line})
    errs = [f for f in fs if f.level == "ERROR"]
    assert len(errs) == 1 and errs[0].kind == "OpenAI/Anthropic sk- 密钥"


def test_suppress_comment_silences_line():
    line = 'K = "sk-abcdefghijklmnopqrstuvwxyz012345"  # release-check: ignore\n'
    assert _audit({"pkg/a.py": line}) == []


# ------------------------------------------------------- 整体卫生检查
def test_sdist_missing_changelog_warns():
    fs = _audit({"pkg/__init__.py": CLEAN_PY}, ".tar.gz", _build_sdist)
    assert len(fs) == 1 and fs[0].kind.startswith("sdist 未包含 CHANGELOG.md")


def test_sdist_with_changelog_no_warn():
    fs = _audit(
        {"pkg/__init__.py": CLEAN_PY, "CHANGELOG.md": "# log\n"},
        ".tar.gz", _build_sdist,
    )
    assert fs == [], _kinds(fs)


def test_wheel_containing_tests_warns():
    fs = _audit({"tests/test_x.py": "x = 1\n"})
    assert len(fs) == 1 and fs[0].kind == "wheel 中包含 tests/ 目录"


def test_sdist_may_contain_tests():
    fs = _audit(
        {"tests/test_x.py": "x = 1\n", "CHANGELOG.md": "# log\n"},
        ".tar.gz", _build_sdist,
    )
    assert fs == [], _kinds(fs)


# ------------------------------------------------------- 脱敏与退出码
def test_mask_hides_secret_body():
    m = check_release._mask("sk-abcdefghijklmnopqrstuvwxyz012345")
    assert m.startswith("sk-abc")
    assert "defghijklmnopqrstuvwxyz" not in m
    assert "35 chars" in m


def test_run_audit_returns_zero_on_clean(tmp_path, capsys):
    _build_wheel(tmp_path / "ok-1.0-py3-none-any.whl", {"pkg/a.py": CLEAN_PY})
    assert check_release.run_audit([str(tmp_path)]) == 0
    assert "通过" in capsys.readouterr().out


def test_run_audit_returns_one_on_dirty(tmp_path):
    _build_wheel(tmp_path / "bad-1.0-py3-none-any.whl", {"pkg/.env": "K=v\n"})
    assert check_release.run_audit([str(tmp_path)]) == 1


def test_run_audit_strict_fails_on_warning(tmp_path):
    _build_sdist(tmp_path / "w-1.0.tar.gz", {"pkg/a.py": CLEAN_PY})
    assert check_release.run_audit([str(tmp_path)]) == 0
    assert check_release.run_audit([str(tmp_path)], strict=True) == 1


def test_run_audit_no_targets_returns_one(tmp_path):
    assert check_release.run_audit([str(tmp_path)]) == 1


def test_collect_targets_expands_directory(tmp_path):
    _build_wheel(tmp_path / "a-1.0-py3-none-any.whl", {"pkg/a.py": CLEAN_PY})
    _build_sdist(tmp_path / "a-1.0.tar.gz", {"pkg/a.py": CLEAN_PY})
    (tmp_path / "notes.txt").write_text("ignore me\n")
    got = check_release.collect_targets([str(tmp_path)])
    assert sorted(os.path.basename(p) for p in got) == [
        "a-1.0-py3-none-any.whl", "a-1.0.tar.gz",
    ]


def test_collect_targets_accepts_single_file(tmp_path):
    art = _build_wheel(tmp_path / "a-1.0-py3-none-any.whl", {"pkg/a.py": CLEAN_PY})
    assert check_release.collect_targets([art]) == [art]


# ------------------------------------------------------- 仓库自身卫生
def test_repo_has_no_banned_files():
    """仓库里不应躺着只该留在本机的配置/密钥文件。"""
    skip_dirs = {".venv", ".git", "__pycache__", ".opencode", "node_modules", ".pytest_cache"}
    bad = []
    for root, dirs, files in os.walk(_REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), _REPO_ROOT)
            hit = check_release.check_member_name(rel)
            if hit and hit[0] == "ERROR":
                bad.append(rel)
    assert bad == []
