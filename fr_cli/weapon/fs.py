"""
虚拟文件系统 (VFS) - 安全沙盒引擎
限制AI和用户只能在允许的目录内操作
"""
import os
from pathlib import Path
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import GREEN, RED, CYAN, DIM, RESET

class VFS:
    def __init__(self, allowed_dirs):
        self.ds = [str(Path(d).resolve()) for d in allowed_dirs]
        self.cwd = self.ds[0] if self.ds else None

    def _resolve(self, p):
        """安全解析路径，防止../逃逸"""
        if not self.cwd: return None
        base = Path(self.cwd)
        target = (base / p).resolve()
        # 检查解析后的路径是否仍在允许的目录树内
        for d in self.ds:
            base_path = str(Path(d).resolve())
            target_str = str(target)
            # 精确匹配或确保是子目录（防止 /foo 匹配 /foo-bar）
            if target_str == base_path or target_str.startswith(base_path + os.sep):
                return target
        return None

    def add(self, p, l):
        try:
            rp = str(Path(p).resolve())
            if not os.path.isdir(rp): return False, f"{RED}{T('err_dir_no', l)}{RESET}"
            if rp not in self.ds:
                self.ds.append(rp)
                if not self.cwd: self.cwd = rp
            return True, f"{GREEN}{T('ok_dir_add', l, rp)}{RESET}"
        except Exception as e: return False, f"{RED}{e}{RESET}"

    def cd(self, p, l):
        if not p: return True, f"{GREEN}{self.cwd}{RESET}"
        # 支持直接切换到已挂载的根目录
        for d in self.ds:
            if Path(p).resolve() == Path(d).resolve():
                self.cwd = d; return True, f"{GREEN}{T('ok_cd', l, self.cwd)}{RESET}"
        
        target = self._resolve(p)
        if not target: return False, f"{RED}{T('err_bound', l)}{RESET}"
        if not target.is_dir(): return False, f"{RED}{T('err_no_file', l)}{RESET}"
        self.cwd = str(target)
        return True, f"{GREEN}{T('ok_cd', l, self.cwd)}{RESET}"

    def ls(self, l):
        if not self.cwd: return None, f"{RED}{T('no_dir', l)}{RESET}"
        try:
            p = Path(self.cwd)
            items = []
            for f in p.iterdir():
                if f.name.startswith('.'): continue
                items.append(f"{CYAN}{f.name}/" if f.is_dir() else f.name)
            return sorted(items), None
        except Exception as e: return None, f"{RED}{e}{RESET}"

    def read(self, fn, l):
        target = self._resolve(fn)
        if not target: return None, f"{RED}{T('err_bound', l)}{RESET}"
        if not target.is_file(): return None, f"{RED}{T('err_no_file', l)}{RESET}"
        try:
            # 尝试多种编码读取
            for enc in ['utf-8', 'gbk', 'latin-1']:
                try: return target.read_text(encoding=enc), None
                except UnicodeDecodeError: continue
            return None, f"{RED}Decode fail{RESET}"
        except Exception as e: return None, f"{RED}{e}{RESET}"
    
    def write(self, fn, content, l, mode='w', encoding='utf-8'):
        """安全写入文件
        
        Args:
            fn: 文件名
            content: 文件内容
            l: 语言
            mode: 写入模式 ('w'=覆盖, 'a'=追加)
            encoding: 文件编码
        
        Returns:
            (success, message)
        """
        target = self._resolve(fn)
        if not target: return False, f"{RED}{T('err_bound', l)}{RESET}"
        
        try:
            # 如果是覆盖模式，检查父目录是否存在
            if mode == 'w':
                parent = target.parent
                if not parent.exists():
                    parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(target, mode, encoding=encoding) as f:
                f.write(content)
            
            return True, f"{GREEN}{T('ok_write', l, str(target))}{RESET}"
        except PermissionError:
            return False, f"{RED}{T('err_write_perm', l)}{RESET}"
        except Exception as e:
            return False, f"{RED}{e}{RESET}"
    
    def append(self, fn, content, l, encoding='utf-8'):
        """追加内容到文件
        
        Args:
            fn: 文件名
            content: 要追加的内容
            l: 语言
            encoding: 文件编码
        
        Returns:
            (success, message)
        """
        return self.write(fn, content, l, mode='a', encoding=encoding)
    
    def exists(self, fn):
        """检查文件是否存在
        
        Args:
            fn: 文件名
        
        Returns:
            bool: 文件是否存在
        """
        target = self._resolve(fn)
        return target is not None and target.exists()
    
    def delete(self, fn, l):
        """删除文件
        
        Args:
            fn: 文件名
            l: 语言
        
        Returns:
            (success, message)
        """
        target = self._resolve(fn)
        if not target: return False, f"{RED}{T('err_bound', l)}{RESET}"
        if not target.exists(): return False, f"{RED}{T('err_no_file', l)}{RESET}"
        
        try:
            target.unlink()
            return True, f"{GREEN}{T('ok_delete', l, str(target))}{RESET}"
        except PermissionError:
            return False, f"{RED}{T('err_write_perm', l)}{RESET}"
        except Exception as e:
            return False, f"{RED}{e}{RESET}"
