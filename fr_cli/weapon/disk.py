"""
云端腾云引擎
支持阿里云 OSS 的简易文件上传下载 (无依赖时提供优雅降级提示)
"""
import os
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import RED, GREEN, DIM

class CloudDisk:
    def __init__(self, cfg):
        self.type = cfg.get("type", "")
        self.client = None
        self.bucket_name = cfg.get("bucket", "")
        self.prefix = cfg.get("prefix", "")
        
        # 动态加载依赖，若无安装则优雅降级
        if self.type == "oss":
            try:
                import oss2
                auth = oss2.Auth(cfg.get('ak', ''), cfg.get('sk', ''))
                self.client = oss2.Bucket(auth, cfg.get('endpoint', ''), self.bucket_name)
            except ImportError:
                self.client = "MISSING:oss2"

    def ls(self, lang):
        """列出云端指定前缀的文件"""
        if not self.client or self.client.startswith("MISSING"):
            lib = self.client.split(":")[1] if self.client else ""
            return None, T("disk_no_cfg", lang) if not lib else T("disk_miss_dep", lang, lib, lib)
        try:
            files = []
            for obj in oss2.ObjectIterator(self.client, prefix=self.prefix):
                # 去除前缀，只显示相对路径
                name = obj.key[len(self.prefix):]
                if name: files.append(name)
            return files, None
        except Exception as e: return None, f"{T('disk_err', lang)} {e}"

    def up(self, local_path, cloud_name, lang):
        """本地文件上传至云端"""
        if not self.client or self.client.startswith("MISSING"):
            lib = self.client.split(":")[1] if self.client else ""
            return False, T("disk_no_cfg", lang) if not lib else T("disk_miss_dep", lang, lib, lib)
        if not os.path.exists(local_path): return False, T("err_no_file", lang)
        try:
            remote_key = self.prefix + cloud_name
            self.client.put_object_from_file(remote_key, local_path)
            return True, T("disk_ok_up", lang, remote_key)
        except Exception as e: return False, f"{T('disk_err', lang)} {e}"

    def down(self, cloud_name, local_path, lang):
        """云端文件下载至本地"""
        if not self.client or self.client.startswith("MISSING"):
            lib = self.client.split(":")[1] if self.client else ""
            return False, T("disk_no_cfg", lang) if not lib else T("disk_miss_dep", lang, lib, lib)
        try:
            remote_key = self.prefix + cloud_name
            self.client.get_object_to_file(remote_key, local_path)
            return True, T("disk_ok_down", lang, local_path)
        except Exception as e: return False, f"{T('disk_err', lang)} {e}"