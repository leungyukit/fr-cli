"""
FANREN CLI TOOL 综合功能测试
覆盖核心安全、VFS、配置、历史、插件、命令解析等模块
"""
import sys
import os
import json
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TestVFS(unittest.TestCase):
    """虚拟文件系统沙盒测试"""

    def setUp(self):
        self.temp_dir = os.path.realpath(tempfile.mkdtemp())
        from fr_cli.weapon.fs import VFS
        self.vfs = VFS([self.temp_dir])

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_path_escape_prevention(self):
        """禁止 ../ 逃逸到允许目录之外"""
        result = self.vfs._resolve("../escape.txt")
        self.assertIsNone(result)

    def test_allowed_path_resolution(self):
        """允许路径正常解析"""
        result = self.vfs._resolve("test.txt")
        self.assertIsNotNone(result)
        self.assertTrue(str(result).startswith(self.temp_dir))

    def test_write_and_read(self):
        """写入与读取卷轴"""
        ok, msg = self.vfs.write("hello.txt", "world", "zh")
        self.assertTrue(ok)
        content, err = self.vfs.read("hello.txt", "zh")
        self.assertIsNone(err)
        self.assertEqual(content, "world")

    def test_append(self):
        """追加内容"""
        self.vfs.write("log.txt", "line1\n", "zh")
        ok, msg = self.vfs.append("log.txt", "line2", "zh")
        self.assertTrue(ok)
        content, err = self.vfs.read("log.txt", "zh")
        self.assertEqual(content, "line1\nline2")

    def test_delete(self):
        """删除卷轴"""
        self.vfs.write("del_me.txt", "bye", "zh")
        self.assertTrue(self.vfs.exists("del_me.txt"))
        ok, msg = self.vfs.delete("del_me.txt", "zh")
        self.assertTrue(ok)
        self.assertFalse(self.vfs.exists("del_me.txt"))

    def test_cd_and_ls(self):
        """穿梭洞府与列目录"""
        subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(subdir)
        ok, msg = self.vfs.cd("subdir", "zh")
        self.assertTrue(ok)
        self.assertEqual(self.vfs.cwd, subdir)
        items, err = self.vfs.ls("zh")
        self.assertIsNone(err)

    def test_read_nonexistent(self):
        """读取不存在的卷轴"""
        content, err = self.vfs.read("ghost.txt", "zh")
        self.assertIsNone(content)
        self.assertIsNotNone(err)

    def test_no_allowed_dirs(self):
        """未开放洞府时的降级"""
        from fr_cli.weapon.fs import VFS
        empty_vfs = VFS([])
        items, err = empty_vfs.ls("zh")
        self.assertIsNone(items)
        self.assertIsNotNone(err)

    def test_list_dirs(self):
        """列出所有已挂载的工作目录"""
        items, err = self.vfs.list_dirs("zh")
        self.assertIsNone(err)
        self.assertEqual(len(items), 1)
        self.assertIn(self.temp_dir, items[0])

    def test_list_dirs_empty(self):
        """未挂载任何目录时列出为空"""
        from fr_cli.weapon.fs import VFS
        empty_vfs = VFS([])
        items, err = empty_vfs.list_dirs("zh")
        self.assertIsNone(items)
        self.assertIsNotNone(err)

    def test_remove_dir_by_index(self):
        """按索引删除工作目录"""
        # 先添加第二个目录
        subdir = os.path.join(self.temp_dir, "sub2")
        os.makedirs(subdir)
        self.vfs.add(subdir, "zh")
        self.assertEqual(len(self.vfs.ds), 2)

        # 按索引 1 删除
        ok, msg = self.vfs.remove_dir("1", "zh")
        self.assertTrue(ok)
        self.assertEqual(len(self.vfs.ds), 1)
        self.assertNotIn(subdir, self.vfs.ds)

    def test_remove_dir_by_path(self):
        """按路径删除工作目录"""
        subdir = os.path.join(self.temp_dir, "sub3")
        os.makedirs(subdir)
        self.vfs.add(subdir, "zh")

        ok, msg = self.vfs.remove_dir(subdir, "zh")
        self.assertTrue(ok)
        self.assertEqual(len(self.vfs.ds), 1)

    def test_remove_dir_cwd_switch(self):
        """删除当前 cwd 时自动切换"""
        subdir = os.path.join(self.temp_dir, "sub4")
        os.makedirs(subdir)
        self.vfs.add(subdir, "zh")
        self.vfs.cd("sub4", "zh")
        self.assertEqual(self.vfs.cwd, subdir)

        ok, msg = self.vfs.remove_dir(subdir, "zh")
        self.assertTrue(ok)
        # cwd 应自动切回剩余的第一个目录
        self.assertEqual(self.vfs.cwd, self.temp_dir)

    def test_remove_dir_invalid_index(self):
        """删除无效的索引应失败"""
        ok, msg = self.vfs.remove_dir("99", "zh")
        self.assertFalse(ok)

    def test_remove_dir_not_mounted(self):
        """删除未挂载的路径应失败"""
        ok, msg = self.vfs.remove_dir("/nonexistent/path", "zh")
        self.assertFalse(ok)


class TestSecurity(unittest.TestCase):
    """四阶安全确认引擎测试"""

    @patch("fr_cli.conf.config.save_config")
    def test_ask_y_once(self, mock_save):
        """Y: 仅此一次放行"""
        from fr_cli.security.security import ask
        with patch("builtins.input", return_value="y"):
            allowed, sconfirm, fconfirm = ask("sec_read", "test.txt", "zh", False, False, {})
        self.assertTrue(allowed)
        self.assertFalse(sconfirm)
        self.assertFalse(fconfirm)

    @patch("fr_cli.conf.config.save_config")
    def test_ask_a_session(self, mock_save):
        """A: 本次轮回放行"""
        from fr_cli.security.security import ask
        with patch("builtins.input", return_value="a"):
            allowed, sconfirm, fconfirm = ask("sec_read", "test.txt", "zh", False, False, {})
        self.assertTrue(allowed)
        self.assertTrue(sconfirm)
        self.assertFalse(fconfirm)

    @patch("fr_cli.security.security.save_config")
    def test_ask_f_forever(self, mock_save):
        """F: 永世放行并写入配置"""
        from fr_cli.security.security import ask
        cfg = {"auto_confirm_forever": False}
        with patch("builtins.input", return_value="f"):
            allowed, sconfirm, fconfirm = ask("sec_read", "test.txt", "zh", False, False, cfg)
        self.assertTrue(allowed)
        self.assertTrue(sconfirm)
        self.assertTrue(fconfirm)
        self.assertTrue(cfg["auto_confirm_forever"])
        mock_save.assert_called_once()

    @patch("fr_cli.conf.config.save_config")
    def test_ask_n_deny(self, mock_save):
        """N/回车: 拒绝"""
        from fr_cli.security.security import ask
        with patch("builtins.input", return_value="n"):
            allowed, sconfirm, fconfirm = ask("sec_read", "test.txt", "zh", False, False, {})
        self.assertFalse(allowed)

    def test_already_fconfirm(self):
        """已永久放行时直接通过"""
        from fr_cli.security.security import ask
        allowed, sconfirm, fconfirm = ask("sec_read", "test.txt", "zh", True, False, {})
        self.assertTrue(allowed)

    def test_already_sconfirm(self):
        """已本次放行时直接通过"""
        from fr_cli.security.security import ask
        allowed, sconfirm, fconfirm = ask("sec_read", "test.txt", "zh", False, True, {})
        self.assertTrue(allowed)


class TestConfig(unittest.TestCase):
    """配置系统测试"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.temp_file.close()
        self.temp_backup = tempfile.NamedTemporaryFile(mode="w", suffix=".json.bak", delete=False)
        self.temp_backup.close()
        self.patch_path = patch(
            "fr_cli.conf.config.CONFIG_FILE", Path(self.temp_file.name)
        )
        self.patch_backup = patch(
            "fr_cli.conf.config.CONFIG_BACKUP", Path(self.temp_backup.name)
        )
        self.patch_path.start()
        self.patch_backup.start()

    def tearDown(self):
        self.patch_path.stop()
        self.patch_backup.stop()
        os.unlink(self.temp_file.name)
        os.unlink(self.temp_backup.name)

    def test_load_default(self):
        """缺失配置时返回安全默认值"""
        from fr_cli.conf.config import load_config
        cfg = load_config()
        self.assertEqual(cfg["model"], "glm-4-flash")
        self.assertEqual(cfg["limit"], 20000)
        self.assertEqual(cfg["lang"], "zh")
        self.assertFalse(cfg["auto_confirm_forever"])

    def test_save_and_load(self):
        """配置持久化读写"""
        from fr_cli.conf.config import load_config, save_config
        cfg = load_config()
        cfg["key"] = "test-key-123"
        cfg["model"] = "glm-4-test"
        save_config(cfg)
        cfg2 = load_config()
        self.assertEqual(cfg2["key"], "test-key-123")
        self.assertEqual(cfg2["model"], "glm-4-test")

    def test_merge_missing_keys(self):
        """旧配置缺少新键时自动补齐"""
        from fr_cli.conf.config import load_config, CONFIG_FILE
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"key": "old"}, f)
        cfg = load_config()
        self.assertEqual(cfg["key"], "old")
        self.assertIn("limit", cfg)
        self.assertEqual(cfg["limit"], 20000)


class TestHistory(unittest.TestCase):
    """会话历史管理测试"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.patch_dir = patch("fr_cli.memory.history.HIST_DIR", Path(self.temp_dir))
        self.patch_dir.start()

    def tearDown(self):
        self.patch_dir.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load(self):
        """保存并加载会话"""
        from fr_cli.memory.history import save_sess, load_sess
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        self.assertTrue(save_sess("test_sess", msgs))
        ok, loaded, name = load_sess(0, "new_sys")
        self.assertTrue(ok)
        self.assertEqual(name, "test_sess")
        self.assertEqual(loaded[0]["content"], "new_sys")  # 系统提示词被覆盖

    def test_get_sessions(self):
        """列出所有会话"""
        from fr_cli.memory.history import save_sess, get_sessions
        save_sess("sess_a", [])
        time.sleep(0.05)
        save_sess("sess_b", [])
        ss = get_sessions()
        self.assertEqual(len(ss), 2)
        names = [s["name"] for s in ss]
        self.assertIn("sess_a", names)
        self.assertIn("sess_b", names)

    def test_export_md(self):
        """导出 Markdown"""
        from fr_cli.memory.history import export_md
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        ok, fname = export_md(msgs, "zh")
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(fname))
        with open(fname, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("hello", content)
        self.assertIn("world", content)
        os.unlink(fname)


class TestPlugin(unittest.TestCase):
    """插件进化引擎测试"""

    def test_extract_code(self):
        """从AI回复中提取Python代码块"""
        from fr_cli.addon.plugin import extract_code
        text = "```python\ndef run(args=''):\n    return 'hello'\n```"
        code = extract_code(text)
        self.assertIn("def run", code)

    def test_extract_code_no_block(self):
        """无代码块时返回空字符串"""
        from fr_cli.addon.plugin import extract_code
        self.assertEqual(extract_code("no code here"), "")

    def test_init_plugins(self):
        """扫描本地插件目录"""
        from fr_cli.addon.plugin import init_plugins, PLUGIN_DIR
        # 临时在插件目录创建一个测试插件
        test_plugin = PLUGIN_DIR / "test_demo_plugin.py"
        test_plugin.write_text("def run(args=''):\n    return 'test'\n", encoding="utf-8")
        plugins = init_plugins()
        self.assertIn("test_demo_plugin", plugins)
        test_plugin.unlink()


class TestCron(unittest.TestCase):
    """结界定时引擎测试"""

    def tearDown(self):
        from fr_cli.weapon.cron import JOBS
        for j in list(JOBS):
            if j["timer"]:
                j["timer"].cancel()
        JOBS.clear()

    def test_add_and_list(self):
        """添加并列出任务"""
        from fr_cli.weapon.cron import add_job, list_jobs
        jid, msg = add_job("echo hello", "3600", "zh")
        self.assertIsNotNone(jid)
        res, err = list_jobs("zh")
        self.assertIsNone(err)
        self.assertEqual(len(res), 1)

    def test_add_invalid_interval(self):
        """非法间隔时间应被拒绝"""
        from fr_cli.weapon.cron import add_job
        jid, msg = add_job("echo hi", "abc", "zh")
        self.assertIsNone(jid)

    def test_del_job(self):
        """删除任务"""
        from fr_cli.weapon.cron import add_job, del_job, list_jobs
        jid, _ = add_job("echo x", "3600", "zh")
        ok, msg = del_job(jid, "zh")
        self.assertTrue(ok)
        res, err = list_jobs("zh")
        self.assertIsNotNone(err)  # 空列表返回错误


class TestWebRaider(unittest.TestCase):
    """互联网游侠本地逻辑测试"""

    def test_html_strip(self):
        """HTML标签剥离逻辑"""
        import re
        html = "<html><script>alert(1)</script><body><p>Hello</p> World</body></html>"
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        self.assertEqual(text, "Hello World")


class TestProcessAICommands(unittest.TestCase):
    """测试AI命令解析与clean文本逻辑（模拟main.py中的核心逻辑）"""

    def test_extract_single_command(self):
        """提取单个命令"""
        pattern = r'【命令：(.*?)】'
        text = "我来查看目录\n【命令：/ls】\n完成"
        commands = __import__("re").findall(pattern, text)
        self.assertEqual(commands, ["/ls"])

    def test_extract_multiple_commands(self):
        """提取多个命令"""
        pattern = r'【命令：(.*?)】'
        text = "【命令：/write a.txt hello】【命令：/cat a.txt】"
        commands = __import__("re").findall(pattern, text)
        self.assertEqual(commands, ["/write a.txt hello", "/cat a.txt"])

    def test_clean_response(self):
        """去除命令标记后应返回干净文本"""
        ai_response = "好的，我来查看。\n【命令：/ls】\n目录内容如下："
        pattern = r'【命令：(.*?)】'
        commands = __import__("re").findall(pattern, ai_response)
        clean = ai_response
        for cmd in commands:
            clean = clean.replace(f"【命令：{cmd}】", "")
        clean = "\n".join(line for line in clean.splitlines() if line.strip())
        self.assertNotIn("【命令", clean)
        self.assertIn("好的，我来查看。", clean)

    def test_no_command(self):
        """无命令时返回原文"""
        pattern = r'【命令：(.*?)】'
        text = "这是一段普通回复"
        commands = __import__("re").findall(pattern, text)
        self.assertEqual(commands, [])


class TestCommandParsing(unittest.TestCase):
    """测试execute_command中的命令解析逻辑"""

    def test_command_split_basic(self):
        """基础命令分词"""
        cmd_str = "/write hello.txt hello world"
        parts = cmd_str.strip().split()
        self.assertEqual(parts[0], "/write")
        self.assertEqual(parts[1], "hello.txt")
        self.assertEqual(" ".join(parts[2:]), "hello world")

    def test_mail_send_parsing(self):
        """/mail_send 应正确分离收件人、主题和正文"""
        u = "/mail_send to@ex.com Subject Line Here is body"
        mail_parts = u.split(maxsplit=3)
        to_addr = mail_parts[1] if len(mail_parts) > 1 else ""
        subject = mail_parts[2] if len(mail_parts) > 2 else ""
        body = mail_parts[3] if len(mail_parts) > 3 else ""
        self.assertEqual(to_addr, "to@ex.com")
        self.assertEqual(subject, "Subject")
        self.assertEqual(body, "Line Here is body")

    def test_disk_down_parsing(self):
        """/disk_down 本地路径解析"""
        cmd_str = "/disk_down remote/path/file.txt local/file.txt"
        parts = cmd_str.strip().split()
        arg1 = parts[1] if len(parts) > 1 else ""
        loc = parts[2] if len(parts) > 2 else arg1.split("/")[-1]
        self.assertEqual(arg1, "remote/path/file.txt")
        self.assertEqual(loc, "local/file.txt")


class TestAliyunDrive(unittest.TestCase):
    """阿里云盘适配器测试"""

    def test_missing_dependency(self):
        """未安装 aligo 时应优雅降级"""
        from unittest.mock import patch
        # 模拟 aligo 不存在
        with patch.dict("sys.modules", {"aligo": None}):
            from fr_cli.weapon.disk import CloudDisk
            disk = CloudDisk({"type": "aliyundrive", "name": "test"})
            self.assertTrue(str(disk.client).startswith("MISSING"))
            res, err = disk.ls("zh")
            self.assertIsNone(res)
            self.assertIn("aligo", err)

    def test_cloud_disk_with_mock(self):
        """使用 Mock 验证 CloudDisk 各方法调用"""
        from unittest.mock import MagicMock, patch
        mock_aligo = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "test.txt"
        mock_file.file_id = "abc123"
        mock_aligo.get_file_list.return_value = [mock_file]
        mock_aligo.refresh_token = "mock_token"

        with patch.dict("sys.modules", {"aligo": MagicMock(Aligo=MagicMock(return_value=mock_aligo))}):
            from fr_cli.weapon.disk import CloudDisk
            # 重新导入以确保使用 patched 模块
            import importlib
            import fr_cli.weapon.disk as disk_module
            importlib.reload(disk_module)
            CloudDisk = disk_module.CloudDisk

            disk = CloudDisk({"type": "aliyundrive", "refresh_token": "rt"})
            self.assertIsNotNone(disk.client)

            # ls
            files, err = disk.ls("zh")
            self.assertIsNone(err)
            self.assertEqual(files, ["📄 test.txt"])
            mock_aligo.get_file_list.assert_called()

            # up
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"hello")
                tmp_path = f.name
            ok, msg = disk.up(tmp_path, "test.txt", "zh")
            self.assertTrue(ok)
            mock_aligo.upload_file.assert_called()
            os.unlink(tmp_path)

            # down
            ok, msg = disk.down("test.txt", "/tmp/test.txt", "zh")
            self.assertTrue(ok)
            mock_aligo.download_file.assert_called()

    def test_ls_distinguishes_folders_and_files(self):
        """ls() 应区分文件和文件夹并返回对应图标"""
        from unittest.mock import MagicMock, patch
        mock_aligo = MagicMock()
        mock_folder = MagicMock()
        mock_folder.name = "docs"
        mock_folder.file_id = "folder1"
        mock_folder.type = "folder"
        mock_file = MagicMock()
        mock_file.name = "readme.txt"
        mock_file.file_id = "file1"
        mock_file.type = "file"
        mock_aligo.get_file_list.return_value = [mock_folder, mock_file]

        with patch.dict("sys.modules", {"aligo": MagicMock(Aligo=MagicMock(return_value=mock_aligo))}):
            import importlib
            import fr_cli.weapon.disk as disk_module
            importlib.reload(disk_module)
            CloudDisk = disk_module.CloudDisk

            disk = CloudDisk({"type": "aliyundrive"})
            items, err = disk.ls("zh")
            self.assertIsNone(err)
            self.assertEqual(len(items), 2)
            self.assertIn("📁 docs", items)
            self.assertIn("📄 readme.txt", items)

    def test_cd_into_subfolder_and_back(self):
        """cd() 应支持进入子目录和返回上级"""
        from unittest.mock import MagicMock, patch
        mock_aligo = MagicMock()
        mock_folder = MagicMock()
        mock_folder.name = "projects"
        mock_folder.file_id = "fid_123"
        mock_folder.type = "folder"
        mock_aligo.get_file_list.return_value = [mock_folder]

        with patch.dict("sys.modules", {"aligo": MagicMock(Aligo=MagicMock(return_value=mock_aligo))}):
            import importlib
            import fr_cli.weapon.disk as disk_module
            importlib.reload(disk_module)
            CloudDisk = disk_module.CloudDisk

            disk = CloudDisk({"type": "aliyundrive"})
            # 先 ls 填充 _path_map
            disk.ls("zh")

            # 进入子目录
            ok, msg = disk.cd("projects", "zh")
            self.assertTrue(ok)
            self.assertEqual(disk._cwd, "fid_123")

            # 返回上级
            ok2, msg2 = disk.cd("..", "zh")
            self.assertTrue(ok2)
            self.assertEqual(disk._cwd, "root")

    def test_cd_back_at_root(self):
        """在根目录执行 cd .. 应失败"""
        from unittest.mock import MagicMock, patch
        mock_aligo = MagicMock()
        mock_aligo.get_file_list.return_value = []

        with patch.dict("sys.modules", {"aligo": MagicMock(Aligo=MagicMock(return_value=mock_aligo))}):
            import importlib
            import fr_cli.weapon.disk as disk_module
            importlib.reload(disk_module)
            CloudDisk = disk_module.CloudDisk

            disk = CloudDisk({"type": "aliyundrive"})
            ok, msg = disk.cd("..", "zh")
            self.assertFalse(ok)


class TestToolCallingLoop(unittest.TestCase):
    """验证工具调用闭环：命令执行后结果应能回传给AI上下文"""

    def test_message_history_update(self):
        """模拟主循环中命令执行后消息列表的更新"""
        messages = [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "帮我查目录"},
        ]
        # AI回复包含命令标记
        ai_text = "好的，我来查看。\n【命令：/ls】"
        cmd_results = ["✅ 命令执行成功: /ls\n   结果: file1.txt\nfile2.txt"]
        clean_txt = "好的，我来查看。"

        # 模拟主循环的更新逻辑
        messages.append({"role": "assistant", "content": ai_text})
        messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
        messages.append({
            "role": "system",
            "content": f"命令执行结果:\n" + "\n".join(cmd_results)
        })

        self.assertEqual(messages[-2]["content"], "好的，我来查看。")
        self.assertIn("命令执行结果", messages[-1]["content"])
        self.assertIn("file1.txt", messages[-1]["content"])


class TestSecurityManager(unittest.TestCase):
    """测试 command/security.py 中的 SecurityManager"""

    @patch("fr_cli.security.security.save_config")
    def test_init_and_fconfirm(self, mock_save):
        from fr_cli.command.security import SecurityManager
        cfg = {"auto_confirm_forever": False}
        sm = SecurityManager("zh", cfg)
        self.assertFalse(sm.fconfirm)
        self.assertFalse(sm.sconfirm)
        with patch("builtins.input", return_value="f"):
            self.assertTrue(sm.check("sec_read", "test.txt"))
        self.assertTrue(sm.fconfirm)
        self.assertTrue(sm.sconfirm)
        mock_save.assert_called_once()

    @patch("fr_cli.command.security.save_config")
    def test_y_once(self, mock_save):
        from fr_cli.command.security import SecurityManager
        sm = SecurityManager("zh", {})
        with patch("builtins.input", return_value="y"):
            self.assertTrue(sm.check("sec_read", "a.txt"))
        self.assertFalse(sm.fconfirm)
        mock_save.assert_not_called()

    def test_already_fconfirm(self):
        from fr_cli.command.security import SecurityManager
        sm = SecurityManager("zh", {"auto_confirm_forever": True})
        self.assertTrue(sm.check("sec_read", "x"))

    def test_already_sconfirm(self):
        from fr_cli.command.security import SecurityManager
        sm = SecurityManager("zh", {})
        sm.sconfirm = True
        self.assertTrue(sm.check("sec_read", "x"))


class TestWeaponLoader(unittest.TestCase):
    """测试 weapon/loader.py 中的武器图谱加载与判定"""

    def test_load_weapon_md_structure(self):
        from fr_cli.weapon.loader import load_weapon_md
        tools, triggers = load_weapon_md()
        self.assertGreater(len(tools), 0)
        names = [t["name"] for t in tools]
        self.assertIn("web_search", names)
        self.assertIn("file_operations", names)
        # 每个工具应有 commands 和 path
        for t in tools:
            self.assertTrue(t["commands"])
            self.assertTrue(t["path"])

    def test_get_available_tools_with_plugins(self):
        from fr_cli.weapon.loader import get_available_tools
        weapon_tools = [{"name": "a", "description": "d", "commands": ["/a"], "path": "p"}]
        plugins = {"demo": "/path/demo.py"}
        tools = get_available_tools(weapon_tools, plugins)
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[1]["name"], "plugin_demo")

    def test_get_available_tools_no_plugins(self):
        from fr_cli.weapon.loader import get_available_tools
        tools = get_available_tools([], None)
        self.assertEqual(tools, [])

    def test_should_inject_tools_hit(self):
        from fr_cli.weapon.loader import should_inject_tools, load_weapon_md
        _, triggers = load_weapon_md()
        self.assertTrue(should_inject_tools("帮我搜索一下", triggers))
        self.assertTrue(should_inject_tools("查看当前目录文件", triggers))
        self.assertTrue(should_inject_tools("发邮件给张三", triggers))

    def test_should_inject_tools_miss(self):
        from fr_cli.weapon.loader import should_inject_tools, load_weapon_md
        _, triggers = load_weapon_md()
        self.assertFalse(should_inject_tools("你好", triggers))
        self.assertFalse(should_inject_tools("1+1等于几", triggers))
        self.assertFalse(should_inject_tools("/ls", triggers))

    def test_should_inject_tools_empty_triggers(self):
        from fr_cli.weapon.loader import should_inject_tools
        self.assertFalse(should_inject_tools("anything", {}))


class TestRecommender(unittest.TestCase):
    """测试 core/recommender.py 功能推荐"""

    def test_recommend_file(self):
        from fr_cli.core.recommender import recommend_features
        recs = recommend_features("帮我查看文件")
        cmds = [r["cmd"] for r in recs]
        self.assertIn("/ls", cmds)
        self.assertIn("/cat <file>", cmds)

    def test_recommend_search(self):
        from fr_cli.core.recommender import recommend_features
        recs = recommend_features("搜索人工智能")
        cmds = [r["cmd"] for r in recs]
        self.assertIn("/web <query>", cmds)

    def test_recommend_none(self):
        from fr_cli.core.recommender import recommend_features
        recs = recommend_features("你好")
        self.assertEqual(recs, [])

    def test_recommend_multiple_categories(self):
        from fr_cli.core.recommender import recommend_features
        recs = recommend_features("保存文件并发送邮件")
        cmds = [r["cmd"] for r in recs]
        self.assertIn("/write <file> <content>", cmds)
        self.assertIn("/mail_inbox", cmds)


class TestCommandExecutor(unittest.TestCase):
    """测试 command/executor.py 命令执行引擎"""

    def setUp(self):
        self.temp_dir = os.path.realpath(tempfile.mkdtemp())
        from fr_cli.weapon.fs import VFS
        from fr_cli.command.security import SecurityManager
        from fr_cli.command.executor import CommandExecutor
        vfs = VFS([self.temp_dir])
        security = SecurityManager("zh", {})
        self.executor = CommandExecutor(
            vfs, None, None, None, {}, "zh", security, {}, None, "glm-4-flash"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_execute_ls_empty(self):
        result, error = self.executor.execute("/ls")
        self.assertIsNone(error)
        self.assertEqual(result, "")

    def test_execute_write_and_cat(self):
        result, error = self.executor.execute("/write hello.txt world")
        self.assertIsNone(error)
        self.assertIn("已刻录", result)

        result, error = self.executor.execute("/cat hello.txt")
        self.assertIsNone(error)
        self.assertEqual(result, "world")

    def test_execute_cd_and_ls(self):
        subdir = os.path.join(self.temp_dir, "sub")
        os.makedirs(subdir)
        result, error = self.executor.execute("/cd sub")
        self.assertIsNone(error)
        self.assertIn("穿梭至", result)

    def test_execute_delete(self):
        self.executor.execute("/write del_me.txt bye")
        result, error = self.executor.execute("/delete del_me.txt")
        self.assertIsNone(error)
        self.assertIn("已销毁", result)

    def test_execute_unknown(self):
        result, error = self.executor.execute("/unknown_cmd")
        self.assertIsNone(result)
        self.assertIn("Unknown command", error)

    def test_execute_empty(self):
        result, error = self.executor.execute("")
        self.assertIsNone(result)
        self.assertEqual(error, "Empty command")

    def test_process_ai_commands_single(self):
        clean, results = self.executor.process_ai_commands("【命令：/ls】")
        self.assertEqual(len(results), 1)
        self.assertIn("✅", results[0])
        self.assertNotIn("【命令", clean)

    def test_process_ai_commands_multiple(self):
        text = "【命令：/write a.txt hello】【命令：/cat a.txt】"
        clean, results = self.executor.process_ai_commands(text)
        self.assertEqual(len(results), 2)
        self.assertNotIn("【命令", clean)

    def test_process_ai_commands_no_command(self):
        clean, results = self.executor.process_ai_commands("这是一段普通回复")
        self.assertEqual(results, [])
        self.assertEqual(clean, "这是一段普通回复")

    def test_process_ai_commands_clean_removes_markers(self):
        text = "好的\n【命令：/ls】\n完成"
        clean, results = self.executor.process_ai_commands(text)
        self.assertNotIn("【命令", clean)
        self.assertIn("好的", clean)
        self.assertIn("完成", clean)


class TestContextMemory(unittest.TestCase):
    """测试 memory/context.py 记忆上下文引擎"""

    def setUp(self):
        from fr_cli.memory.context import clear_context
        clear_context("test_sess")
        clear_context("")

    def tearDown(self):
        from fr_cli.memory.context import clear_context
        clear_context("test_sess")
        clear_context("")

    def test_extract_recent_turns_basic(self):
        from fr_cli.memory.context import extract_recent_turns
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "how are you"},
            {"role": "assistant", "content": "fine"},
        ]
        turns = extract_recent_turns(messages, 5)
        self.assertEqual(len(turns), 4)  # 排除 system
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[0]["content"], "hi")

    def test_extract_recent_turns_limit(self):
        from fr_cli.memory.context import extract_recent_turns
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"u{i}"})
            messages.append({"role": "assistant", "content": f"a{i}"})
        turns = extract_recent_turns(messages, 5)
        self.assertEqual(len(turns), 10)  # 5 轮 = 10 条消息
        self.assertEqual(turns[-1]["content"], "a19")

    def test_extract_recent_turns_skips_system(self):
        from fr_cli.memory.context import extract_recent_turns
        messages = [
            {"role": "system", "content": "sys1"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "命令结果"},
            {"role": "assistant", "content": "final"},
        ]
        turns = extract_recent_turns(messages, 5)
        self.assertEqual(len(turns), 3)  # 排除两条 system

    def test_build_context_summary_zh(self):
        from fr_cli.memory.context import build_context_summary
        turns = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "有什么可以帮你的？"},
        ]
        summary = build_context_summary(turns, "zh")
        self.assertIn("当前会话上下文摘要", summary)
        self.assertIn("用户：你好", summary)
        self.assertIn("AI：有什么可以帮你的？", summary)

    def test_build_context_summary_en(self):
        from fr_cli.memory.context import build_context_summary
        turns = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        summary = build_context_summary(turns, "en")
        self.assertIn("Session Context Summary", summary)

    def test_build_context_summary_empty(self):
        from fr_cli.memory.context import build_context_summary
        self.assertEqual(build_context_summary([]), "")

    def test_build_context_summary_removes_commands(self):
        from fr_cli.memory.context import build_context_summary
        turns = [
            {"role": "assistant", "content": "好的\n【命令：/ls】"},
        ]
        summary = build_context_summary(turns, "zh")
        self.assertNotIn("【命令", summary)

    def test_build_context_summary_truncate(self):
        from fr_cli.memory.context import build_context_summary
        long_text = "x" * 500
        turns = [{"role": "user", "content": long_text}]
        summary = build_context_summary(turns, "zh")
        self.assertIn("...", summary)
        self.assertLess(len(summary), 400)

    def test_build_context_summary_multimodal(self):
        from fr_cli.memory.context import build_context_summary
        turns = [{"role": "user", "content": [{"type": "image_url", "url": "..."}]}]
        summary = build_context_summary(turns, "zh")
        self.assertIn("[图片/多模态消息]", summary)

    def test_save_and_load_context(self):
        from fr_cli.memory.context import save_context, load_context
        save_context("test_sess", "这是测试上下文")
        loaded = load_context("test_sess")
        self.assertEqual(loaded, "这是测试上下文")

    def test_load_nonexistent_context(self):
        from fr_cli.memory.context import load_context
        self.assertEqual(load_context("ghost_session"), "")

    def test_clear_context(self):
        from fr_cli.memory.context import save_context, load_context, clear_context
        save_context("test_sess", "data")
        self.assertEqual(load_context("test_sess"), "data")
        clear_context("test_sess")
        self.assertEqual(load_context("test_sess"), "")

    def test_default_session(self):
        from fr_cli.memory.context import save_context, load_context
        save_context("", "default_ctx")
        self.assertEqual(load_context(""), "default_ctx")


if __name__ == "__main__":
    unittest.main(verbosity=2)
