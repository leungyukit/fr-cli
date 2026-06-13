"""
虚拟文件系统 (VFS) - 安全沙盒引擎
限制AI和用户只能在允许的目录内操作
"""
import difflib
import os
from pathlib import Path
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import GREEN, RED, CYAN, YELLOW, DIM, RESET
from fr_cli.core.result import Result


def _is_binary_content(data: bytes) -> bool:
    """简单启发式判断内容是否为二进制"""
    if not data:
        return False
    # 若包含空字节，则认为是二进制
    if b"\x00" in data:
        return True
    # 尝试用 utf-8 解码，失败则视为二进制
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _format_diff(old_lines: list, new_lines: list, path: str, l: str = "zh", max_lines: int = 80) -> str:
    """生成带颜色的统一格式 diff 文本"""
    # path 可能是绝对路径，使用文件名作为 diff 标签更简洁
    label = Path(path).name
    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        lineterm="",
    ))
    if not diff:
        return ""

    truncated = False
    if len(diff) > max_lines:
        diff = diff[:max_lines]
        truncated = True

    lines = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            lines.append(f"{CYAN}{line}{RESET}")
        elif line.startswith("+"):
            lines.append(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            lines.append(f"{RED}{line}{RESET}")
        else:
            lines.append(line)

    if truncated:
        lines.append(f"{YELLOW}{T('diff_truncated', l)}{RESET}")

    return "\n".join(lines)


def _preview_content(content: str, l: str = "zh", max_lines: int = 20) -> str:
    """生成新文件/追加内容的颜色预览"""
    lines = content.splitlines()
    if not lines:
        return ""
    truncated = len(lines) > max_lines
    preview = lines[:max_lines]
    result = "\n".join(f"{GREEN}+{line}{RESET}" for line in preview)
    if truncated:
        result += f"\n{YELLOW}{T('diff_preview_truncated', l, len(preview))}{RESET}"
    return result

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

    def check(self, p, l="zh"):
        """检查路径是否在沙盒允许范围内，返回 Result[bool]。"""
        target = self._resolve(p)
        if target is None:
            return Result.fail(T("err_bound", l))
        return Result.ok(True)

    def add(self, p, l):
        try:
            rp = str(Path(p).resolve())
            if not os.path.isdir(rp): return Result.fail(f"{RED}{T('err_dir_no', l)}{RESET}")
            if rp not in self.ds:
                self.ds.append(rp)
                if not self.cwd: self.cwd = rp
            return Result.ok(f"{GREEN}{T('ok_dir_add', l, rp)}{RESET}")
        except Exception as e: return Result.fail(f"{RED}{e}{RESET}")

    def cd(self, p, l):
        if not p: return Result.ok(f"{GREEN}{self.cwd}{RESET}")
        # 支持直接切换到已挂载的根目录
        for d in self.ds:
            if Path(p).resolve() == Path(d).resolve():
                self.cwd = d; return Result.ok(f"{GREEN}{T('ok_cd', l, self.cwd)}{RESET}")

        target = self._resolve(p)
        if not target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if not target.is_dir(): return Result.fail(f"{RED}{T('err_no_file', l)}{RESET}")
        self.cwd = str(target)
        return Result.ok(f"{GREEN}{T('ok_cd', l, self.cwd)}{RESET}")

    def ls(self, l):
        if not self.cwd: return Result.fail(f"{RED}{T('no_dir', l)}{RESET}")
        try:
            p = Path(self.cwd)
            items = []
            for f in p.iterdir():
                if f.name.startswith('.'): continue
                items.append(f"{CYAN}{f.name}/" if f.is_dir() else f.name)
            return Result.ok(sorted(items))
        except Exception as e: return Result.fail(f"{RED}{e}{RESET}")

    def read(self, fn, l):
        target = self._resolve(fn)
        if not target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if not target.is_file(): return Result.fail(f"{RED}{T('err_no_file', l)}{RESET}")
        try:
            # 尝试多种编码读取
            for enc in ['utf-8', 'gbk', 'latin-1']:
                try: return Result.ok(target.read_text(encoding=enc))
                except UnicodeDecodeError: continue
            return Result.fail(f"{RED}Decode fail{RESET}")
        except Exception as e: return Result.fail(f"{RED}{e}{RESET}")

    def write(self, fn, content, l, mode='w', encoding='utf-8'):
        """安全写入文件，返回 Result。

        覆盖已有文件时会显示统一 diff，追加/新建文件时显示内容预览。

        Args:
            fn: 文件名
            content: 文件内容
            l: 语言
            mode: 写入模式 ('w'=覆盖, 'a'=追加)
            encoding: 文件编码
        """
        target = self._resolve(fn)
        if not target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")

        try:
            # 确保父目录存在（覆盖和追加模式都需要）
            parent = target.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)

            # 生成变更展示
            output_lines = []
            is_new = not target.exists()
            is_overwrite = mode == 'w' and target.exists()
            is_append = mode == 'a' and target.exists()

            if is_new:
                preview = _preview_content(content, l)
                if preview:
                    output_lines.append(f"{CYAN}{T('diff_new_file', l, str(target))}{RESET}")
                    output_lines.append(preview)
            elif is_overwrite:
                try:
                    old_bytes = target.read_bytes()
                    if _is_binary_content(old_bytes):
                        output_lines.append(f"{YELLOW}{T('diff_no_binary', l, str(target))}{RESET}")
                    else:
                        old_text = old_bytes.decode("utf-8")
                        old_lines = old_text.splitlines(keepends=True)
                        new_lines = content.splitlines(keepends=True)
                        diff_text = _format_diff(old_lines, new_lines, str(target), l)
                        if diff_text:
                            output_lines.append(f"{CYAN}{T('diff_overwrite', l, str(target))}{RESET}")
                            output_lines.append(diff_text)
                except Exception:
                    # 读取旧内容失败时跳过 diff 展示
                    pass
            elif is_append:
                preview = _preview_content(content, l)
                if preview:
                    output_lines.append(f"{CYAN}{T('diff_append', l, str(target))}{RESET}")
                    output_lines.append(preview)

            # 写入文件
            with open(target, mode, encoding=encoding) as f:
                f.write(content)

            if output_lines:
                print("\n".join(output_lines))

            return Result.ok(f"{GREEN}{T('ok_write', l, str(target))}{RESET}")
        except PermissionError:
            return Result.fail(f"{RED}{T('err_write_perm', l)}{RESET}")
        except Exception as e:
            return Result.fail(f"{RED}{e}{RESET}")

    def append(self, fn, content, l, encoding='utf-8'):
        """追加内容到文件，返回 Result。"""
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
        """删除文件，返回 Result。"""
        target = self._resolve(fn)
        if not target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if not target.exists(): return Result.fail(f"{RED}{T('err_no_file', l)}{RESET}")

        try:
            target.unlink()
            return Result.ok(f"{GREEN}{T('ok_delete', l, str(target))}{RESET}")
        except PermissionError:
            return Result.fail(f"{RED}{T('err_write_perm', l)}{RESET}")
        except Exception as e:
            return Result.fail(f"{RED}{e}{RESET}")

    def rename(self, old, new, l):
        """重命名文件或目录（沙盒内），返回 Result。"""
        old_target = self._resolve(old)
        if not old_target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if not old_target.exists(): return Result.fail(f"{RED}{T('err_no_file', l)}{RESET}")

        new_target = self._resolve(new)
        if not new_target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if new_target.exists(): return Result.fail(f"{RED}目标已存在: {new_target}{RESET}")

        try:
            new_target.parent.mkdir(parents=True, exist_ok=True)
            old_target.rename(new_target)
            return Result.ok(f"{GREEN}{T('ok_rename', l, str(old_target), str(new_target))}{RESET}")
        except PermissionError:
            return Result.fail(f"{RED}{T('err_write_perm', l)}{RESET}")
        except Exception as e:
            return Result.fail(f"{RED}{e}{RESET}")

    def replace_text(self, fn, old_text, new_text, use_regex, l):
        """替换文件中的文本（支持普通文本和正则表达式），返回 Result。"""
        import re
        target = self._resolve(fn)
        if not target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if not target.is_file(): return Result.fail(f"{RED}{T('err_no_file', l)}{RESET}")

        try:
            for enc in ['utf-8', 'gbk', 'latin-1']:
                try:
                    text = target.read_text(encoding=enc)
                    encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return Result.fail(f"{RED}Decode fail{RESET}")

            if use_regex:
                try:
                    new_content, count = re.subn(old_text, new_text, text)
                except re.error as e:
                    return Result.fail(f"{RED}正则表达式错误: {e}{RESET}")
            else:
                count = text.count(old_text)
                new_content = text.replace(old_text, new_text)

            if count == 0:
                return Result.fail(f"{YELLOW}未找到匹配内容{RESET}")

            # 生成 diff 预览
            old_lines = text.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff_text = _format_diff(old_lines, new_lines, str(target), l)
            if diff_text:
                print(f"{CYAN}{T('diff_replace', l, str(target), count)}{RESET}")
                print(diff_text)

            with open(target, 'w', encoding=encoding) as f:
                f.write(new_content)

            return Result.ok(f"{GREEN}{T('ok_replace', l, count, str(target))}{RESET}")
        except PermissionError:
            return Result.fail(f"{RED}{T('err_write_perm', l)}{RESET}")
        except Exception as e:
            return Result.fail(f"{RED}{e}{RESET}")

    def grep_text(self, fn, pattern, use_regex, l, context=2, max_results=100):
        """在文件中搜索文本（支持普通文本和正则表达式），返回 Result。"""
        import re
        target = self._resolve(fn)
        if not target: return Result.fail(f"{RED}{T('err_bound', l)}{RESET}")
        if not target.is_file(): return Result.fail(f"{RED}{T('err_no_file', l)}{RESET}")

        try:
            for enc in ['utf-8', 'gbk', 'latin-1']:
                try:
                    text = target.read_text(encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return Result.fail(f"{RED}Decode fail{RESET}")

            lines = text.splitlines()

            if use_regex:
                try:
                    compiled = re.compile(pattern)
                except re.error as e:
                    return Result.fail(f"{RED}正则表达式错误: {e}{RESET}")
                matches = [(i, line) for i, line in enumerate(lines) if compiled.search(line)]
            else:
                matches = [(i, line) for i, line in enumerate(lines) if pattern in line]

            if not matches:
                return Result.ok(T('grep_no_match', l, pattern, str(target)))

            results = []
            shown = set()
            total = len(matches)
            truncated = total > max_results
            matches = matches[:max_results]

            for idx, (line_no, line) in enumerate(matches):
                start = max(0, line_no - context)
                end = min(len(lines), line_no + context + 1)
                # 避免相邻匹配重复打印上下文
                if start in shown and idx > 0:
                    pass
                else:
                    if idx > 0:
                        results.append(f"{DIM}...{RESET}")
                    shown.clear()

                for i in range(start, end):
                    if i in shown:
                        continue
                    shown.add(i)
                    num = i + 1
                    content = lines[i]
                    marker = ">>" if i == line_no else "  "
                    results.append(f"{CYAN}{marker}{num:4d}{RESET} {content}")

            header = T('grep_header', l, total, str(target))
            if truncated:
                header += f" {T('grep_truncated', l, max_results)}"
            return Result.ok(f"{header}\n" + "\n".join(results))
        except Exception as e:
            return Result.fail(f"{RED}{e}{RESET}")

    def list_dirs(self, l):
        """列出所有已挂载的工作目录（目录），返回 Result。"""
        if not self.ds:
            return Result.fail(f"{RED}{T('no_dir', l)}{RESET}")
        items = []
        for i, d in enumerate(self.ds):
            marker = f" {GREEN}[{T('cur_dir', l)}]{RESET}" if d == self.cwd else ""
            items.append(f"  [{i}] {CYAN}{d}{RESET}{marker}")
        return Result.ok(items)

    def remove_dir(self, p, l):
        """从允许列表中移除指定工作目录，返回 Result。

        支持按索引或绝对/相对路径删除。
        若移除的是当前 cwd，自动切换到剩余目录中的第一个。
        """
        if not self.ds:
            return Result.fail(f"{RED}{T('no_dir', l)}{RESET}")

        # 尝试按索引解析
        try:
            idx = int(p)
            if idx < 0 or idx >= len(self.ds):
                return Result.fail(f"{RED}{T('err_dir_idx', l)}{RESET}")
            removed = self.ds.pop(idx)
        except ValueError:
            # 按路径解析
            rp = str(Path(p).resolve())
            if rp not in self.ds:
                return Result.fail(f"{RED}{T('err_dir_not_mounted', l, rp)}{RESET}")
            self.ds.remove(rp)
            removed = rp

        # 若删除的是当前 cwd，自动切换
        if self.cwd == removed:
            self.cwd = self.ds[0] if self.ds else None

        return Result.ok(f"{GREEN}{T('ok_dir_remove', l, removed)}{RESET}")
