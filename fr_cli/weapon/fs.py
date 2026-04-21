"""
虚拟文件系统 (VFS) - 安全沙盒引擎
限制AI和用户只能在允许的目录内操作
"""
import os
from pathlib import Path
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import GREEN, RED, CYAN, RESET

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
            base_path = Path(d).resolve()
            try:
                # 使用 relative_to 精确判断是否为目标目录的子路径
                # 可正确处理根目录（/）及避免 /foo 错误匹配 /foo-bar 的前缀问题
                target.relative_to(base_path)
                return target
            except ValueError:
                continue
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
            # 确保父目录存在（覆盖和追加模式都需要）
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

    def list_dirs(self, l):
        """列出所有已挂载的工作目录（洞府）
        
        Returns:
            (列表, None) 或 (None, 错误信息)
        """
        if not self.ds:
            return None, f"{RED}{T('no_dir', l)}{RESET}"
        items = []
        for i, d in enumerate(self.ds):
            marker = f" {GREEN}[{T('cur_dir', l)}]{RESET}" if d == self.cwd else ""
            items.append(f"  [{i}] {CYAN}{d}{RESET}{marker}")
        return items, None

    def remove_dir(self, p, l):
        """从允许列表中移除指定工作目录
        
        支持按索引或绝对/相对路径删除。
        若移除的是当前 cwd，自动切换到剩余目录中的第一个。
        
        Args:
            p: 索引字符串或路径
            l: 语言
        
        Returns:
            (success, message)
        """
        if not self.ds:
            return False, f"{RED}{T('no_dir', l)}{RESET}"

        # 尝试按索引解析
        try:
            idx = int(p)
            if idx < 0 or idx >= len(self.ds):
                return False, f"{RED}{T('err_dir_idx', l)}{RESET}"
            removed = self.ds.pop(idx)
        except ValueError:
            # 按路径解析
            rp = str(Path(p).resolve())
            if rp not in self.ds:
                return False, f"{RED}{T('err_dir_not_mounted', l, rp)}{RESET}"
            self.ds.remove(rp)
            removed = rp

        # 若删除的是当前 cwd，自动切换
        if self.cwd == removed:
            self.cwd = self.ds[0] if self.ds else None

        return True, f"{GREEN}{T('ok_dir_remove', l, removed)}{RESET}"
