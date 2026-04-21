"""
会话轮回管理引擎
负责对话历史的本地保存、加载、删除与 Markdown 导出
"""
import json, os
from pathlib import Path
from datetime import datetime
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import RED, RESET

HIST_DIR = Path.home() / ".zhipu_cli_history"

def init_history():
    """确保历史目录存在"""
    HIST_DIR.mkdir(parents=True, exist_ok=True)

def _fpath(name):
    return HIST_DIR / f"{name}.json"

def get_sessions():
    """获取所有会话列表"""
    init_history()
    sess = []
    for f in sorted(HIST_DIR.glob("sess_*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            sess.append({"file": f.name, "name": data.get("name", f.stem)})
        except: pass
    return sess

def save_sess(name, msgs):
    """保存当前对话到轮回石"""
    init_history()
    safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"sess_{ts}_{safe_name}"
    fp = _fpath(fname)
    try:
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump({"name": name, "ts": ts, "msgs": msgs}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e: 
        print(f"{RED}{e}{RESET}")
        return False

def load_sess(index, sp):
    """从轮回石中加载指定索引的会话"""
    ss = get_sessions()
    if not ss or index >= len(ss): return False, None, None
    fp = HIST_DIR / ss[index]["file"]
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
        msgs = data.get("msgs", [])
        # 强制覆盖第一条为最新的系统提示词
        if msgs and msgs[0]["role"] == "system":
            msgs[0]["content"] = sp
        else:
            msgs.insert(0, {"role": "system", "content": sp})
        return True, msgs, data.get("name")
    except Exception as e: 
        print(f"{RED}{e}{RESET}")
        return False, None, None

def del_sess(index):
    """斩断一段因果(删除会话)"""
    ss = get_sessions()
    if not ss or index >= len(ss): return
    fp = HIST_DIR / ss[index]["file"]
    try: os.remove(fp); return True
    except: return False

def export_md(msgs, lang, out_dir=None):
    """将当前会话导出为 Markdown 文件
    :param out_dir: 用户设定的工作目录，若提供且存在则保存到该目录，否则保存到当前运行目录
    """
    if not msgs: return False, T("empty", lang)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"glm_export_{ts}.md"
    try:
        target_dir = out_dir if out_dir and os.path.isdir(out_dir) else "."
        fpath = os.path.join(target_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            for m in msgs:
                role = m.get("role", "unknown")
                content = m.get("content", "")
                if role == "system": continue
                tag = "### 🧑 凡人" if role == "user" else "### 🧙 飞书"
                f.write(f"{tag}\n\n{content}\n\n---\n\n")
        return True, fpath
    except Exception as e: return False, str(e)