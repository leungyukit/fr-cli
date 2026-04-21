"""
云端腾云引擎
支持阿里云盘（aligo）的文件及目录结构获取、上传、下载
"""
import os
import logging
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import RED, GREEN, RESET

class CloudDisk:
    def __init__(self, cfg):
        self.type = cfg.get("type", "")
        self.client = None
        self._name = cfg.get("name", "fr-cli")
        self._cwd = "root"          # 当前云盘目录 ID
        self._path_map = {}         # 名称 -> {file_id, type, parent_id}
        self._cwd_stack = [("root", "/")]  # 目录历史栈，支持 cd ..

        if self.type == "aliyundrive":
            try:
                from aligo import Aligo
                # 抑制 aligo 及其子模块的 INFO 日志输出（避免显示 HTTP POST 调用详情）
                for logger_name in list(logging.root.manager.loggerDict.keys()):
                    if logger_name.startswith("aligo") or logger_name == "fr-cli":
                        logging.getLogger(logger_name).setLevel(logging.WARNING)
                refresh_token = cfg.get("refresh_token")
                if refresh_token:
                    self.client = Aligo(name=self._name, refresh_token=refresh_token)
                else:
                    self.client = Aligo(name=self._name)
            except ImportError:
                self.client = "MISSING:aligo"
            except Exception as e:
                self.client = f"ERR:{e}"

    def _check_client(self, lang):
        """检查客户端状态并返回错误信息"""
        if not self.client:
            return None, T("disk_no_cfg", lang)
        if isinstance(self.client, str):
            if self.client.startswith("MISSING:"):
                lib = self.client.split(":")[1]
                return None, T("disk_miss_dep", lang, lib, lib)
            if self.client.startswith("ERR:"):
                return None, f"{T('disk_err', lang)} {self.client[4:]}"
        return self.client, None

    def ls(self, lang):
        """列出当前云盘目录的文件和文件夹（带类型标识）"""
        client, err = self._check_client(lang)
        if err:
            return None, err
        try:
            files = client.get_file_list(parent_file_id=self._cwd)
            self._path_map = {}
            items = []
            for f in files:
                is_folder = getattr(f, "type", "") == "folder"
                self._path_map[f.name] = {
                    "file_id": f.file_id,
                    "type": f.type,
                    "parent_id": self._cwd,
                }
                prefix = "📁" if is_folder else "📄"
                items.append(f"{prefix} {f.name}")
            return items, None
        except Exception as e:
            return None, f"{T('disk_err', lang)} {e}"

    def cd(self, path, lang):
        """切换云盘目录，支持 .. 返回上级"""
        client, err = self._check_client(lang)
        if err:
            return False, err

        if path == "..":
            if len(self._cwd_stack) <= 1:
                return False, f"{RED}已在根目录{RESET}"
            self._cwd_stack.pop()
            self._cwd = self._cwd_stack[-1][0]
            return True, f"{GREEN}✅ 已切换至: {self._cwd_stack[-1][1]}{RESET}"

        # 进入子目录：先刷新当前目录列表
        self.ls(lang)
        file_info = self._path_map.get(path)
        if not file_info:
            return False, f"{RED}⚠️ 目录不存在: {path}{RESET}"
        if file_info["type"] != "folder":
            return False, f"{RED}⚠️ {path} 不是目录{RESET}"

        self._cwd = file_info["file_id"]
        self._cwd_stack.append((file_info["file_id"], path))
        return True, f"{GREEN}✅ 已穿梭至: {path}{RESET}"

    def up(self, local_path, cloud_name, lang):
        """本地文件上传至当前云盘目录"""
        client, err = self._check_client(lang)
        if err:
            return False, err
        if not os.path.exists(local_path):
            return False, T("err_no_file", lang)
        try:
            result = client.upload_file(
                file_path=local_path,
                parent_file_id=self._cwd,
                name=cloud_name
            )
            self._path_map[result.name] = {
                "file_id": result.file_id,
                "type": "file",
                "parent_id": self._cwd,
            }
            return True, T("disk_ok_up", lang, result.name)
        except Exception as e:
            return False, f"{T('disk_err', lang)} {e}"

    def down(self, cloud_name, local_path, lang):
        """从当前云盘目录下载文件"""
        client, err = self._check_client(lang)
        if err:
            return False, err

        file_info = self._path_map.get(cloud_name)
        if not file_info:
            self.ls(lang)
            file_info = self._path_map.get(cloud_name)

        if not file_info:
            return False, T("err_no_file", lang)
        if file_info["type"] == "folder":
            return False, f"{RED}⚠️ {cloud_name} 是文件夹，暂不支持单文件下载方式下载文件夹{RED}"

        try:
            local_folder = os.path.dirname(local_path) or "."
            client.download_file(
                file_id=file_info["file_id"],
                local_folder=local_folder
            )
            return True, T("disk_ok_down", lang, local_path)
        except Exception as e:
            return False, f"{T('disk_err', lang)} {e}"
