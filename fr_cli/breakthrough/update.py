"""
自动更新模块 update.py
接口地址: https://up.seeknew.cn/v1/cliupdate
"""
import os, sys, json, platform, subprocess, shutil, tempfile, time, zipfile, hashlib
from pathlib import Path
from typing import Callable, Optional, Tuple

from fr_cli.core.result import Result

UPDATE_API_URL = "https://up.seeknew.cn/v1/cliupdate"
REQUEST_TIMEOUT = 15
PROJECT_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_ROOT / "__version__.txt"

def _read_local_version() -> str:
    try:
        if VERSION_FILE.is_file():
            txt = VERSION_FILE.read_text(encoding="utf-8").strip()
            if txt:
                first_line = txt.splitlines()[0].strip().lower().lstrip('v')
                return first_line
    except Exception: pass
    # Fallback to package __version__
    try:
        from fr_cli import __version__
        return str(__version__).strip().lower().lstrip('v')
    except Exception:
        return "0.0.0"

def _save_local_version(version: str) -> None:
    try: VERSION_FILE.write_text(str(version).strip() + "\n", encoding="utf-8")
    except Exception: pass

def _parse_version_tuple(v: str) -> Tuple[int, ...]:
    parts = v.replace("-", ".").split(".")
    nums = []
    for p in parts:
        p = p.strip(); num = 0
        if p and p[0].isdigit():
            i = 0
            while i < len(p) and p[i].isdigit(): i += 1
            num = int(p[:i])
        nums.append(num)
    while len(nums) < 3: nums.append(0)
    return tuple(nums[:3])

def _is_newer(remote: str, local: str) -> bool:
    return _parse_version_tuple(remote) > _parse_version_tuple(local)

def _fetch_info() -> Result:
    try:
        import urllib.request, ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(UPDATE_API_URL, method="GET", headers={
            "Accept": "application/json", "User-Agent": f"cli-update/{platform.system()}"
        })
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if isinstance(data, dict) and "version" in data and "download_url" in data: return Result.ok(data)
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
                inner = data["data"]
                if "version" in inner and "download_url" in inner: return Result.ok(inner)
            return Result.fail("Unrecognized schema.")
    except Exception as e: return Result.fail(str(e))

def _download(url: str) -> Result:
    try:
        import urllib.request, ssl
        req = urllib.request.Request(url, headers={"User-Agent": "cli-update/1.0"})
        with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as resp:
            data = resp.read()
            return Result.ok(data) if data else Result.fail("Empty payload.")
    except Exception as e: return Result.fail(str(e))

def _apply_source_zip(zip_bytes: bytes, root: Path) -> Result:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "u.zip"; zpath.write_bytes(zip_bytes)
            ext = Path(tmp) / "ext"
            with zipfile.ZipFile(zpath, 'r') as zf: zf.extractall(ext)

            safe_exts = {".py",".sh",".bat",".md",".txt",".toml",".yaml",".yml",".html",".css",".js",".png",".jpg",".gif"}
            skip = {"__version__.txt", "__config__.json"}
            skip_dirs = {"data", "logs", "__pycache__", ".git", ".idea"}

            for r, dirs, files in os.walk(ext):
                rp = Path(r).relative_to(ext)
                if any(p in skip_dirs for p in rp.parts): continue
                for n in files:
                    s = Path(r) / n; d = root / rp / n
                    if n in skip or n.startswith(".") or d.suffix.lower() not in safe_exts: continue
                    try:
                        d.parent.mkdir(parents=True, exist_ok=True)
                        if d.exists():
                            shutil.copy2(str(d), str(d.with_suffix(d.suffix+".bak")))
                        shutil.copy2(str(s), str(d))
                    except Exception: pass
            return Result.ok("OK")
    except Exception as e: return Result.fail(str(e))

def update_check(local_version: Optional[str] = None, verbose: bool = False) -> Result:
    """检查更新。成功时 data 为 (has_update, info_dict)。"""
    lv = local_version or _read_local_version()
    if verbose: print(f"[Update] Local: {lv}")
    info_result = _fetch_info()
    if info_result.is_fail(): return Result.fail(info_result.error)
    info = info_result.unwrap()
    rv = info.get("version", "0.0.0")
    if verbose: print(f"[Update] Remote: {rv}")
    return Result.ok((_is_newer(rv, lv), info))

def update_and_restart(local_version: Optional[str] = None, verbose: bool = False, allow_restart: bool = True, on_before_restart: Optional[Callable] = None) -> Result:
    chk = update_check(local_version, verbose)
    if chk.is_fail(): return Result.fail(chk.error)
    has, info = chk.unwrap()
    if not has or not info: return Result.ok("Already up to date.")

    data_result = _download(info.get("download_url", ""))
    if data_result.is_fail(): return Result.fail(data_result.error)
    data = data_result.unwrap()
    if not data: return Result.fail("Download failed.")

    sha_exp = info.get("sha256")
    if sha_exp and hashlib.sha256(data).hexdigest().lower() != sha_exp.lower():
        return Result.fail("SHA256 mismatch.")

    ftype = info.get("file_type", "source_zip")
    nver = info.get("version", "")

    if ftype == "source_zip":
        apply_result = _apply_source_zip(data, PROJECT_ROOT)
        if apply_result.is_fail(): return Result.fail(apply_result.error)
        _save_local_version(nver)
        if allow_restart:
            if on_before_restart: on_before_restart()
            subprocess.Popen([sys.executable, str(PROJECT_ROOT / "main.py")], cwd=str(PROJECT_ROOT))
            time.sleep(0.5)
            sys.stdout.flush()
            sys.stderr.flush()
            sys.exit(0)
        return Result.ok(f"Updated to {nver}. Please restart.")
    else:
        fname = os.path.basename(info.get("download_url", "update.bin"))
        (PROJECT_ROOT / fname).write_bytes(data)
        return Result.ok(f"Saved {fname}. Please update manually.")

def cli_entry(args=None):
    args = args or sys.argv[1:]
    if not args or args[0].lower() == "check":
        chk = update_check(verbose=True)
        if chk.is_fail(): print(f"Check failed: {chk.error}"); return 1
        has, info = chk.unwrap()
        if not has: print("Already up to date."); return 0
        print(f"New version: {info.get('version')}\nNote: {info.get('release_note', '')}"); return 0
    elif args[0].lower() == "run":
        result = update_and_restart(verbose=True)
        print(f"{'Success' if result.is_ok() else 'Failed'}: {result.unwrap_or(result.error)}")
        return 0 if result.is_ok() else 1
    else:
        print("Usage: python update.py check | run"); return 2

if __name__ == "__main__": sys.exit(cli_entry())
