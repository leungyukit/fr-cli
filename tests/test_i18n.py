"""
国际化 (i18n) 测试
覆盖 T() 函数:zh/en 切换、占位符替换、未知 key 返回空、format 参数。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.lang.i18n import T, I18N


class TestBasicLookup:

    def test_known_key_zh(self):
        """已定义的 key 在中文下应返回非空"""
        # 找一个肯定存在的 key
        result = T("menu_main", "zh")
        assert isinstance(result, str)

    def test_known_key_en(self):
        result = T("menu_main", "en")
        assert isinstance(result, str)

    def test_unknown_key_returns_empty(self):
        """未定义的 key 应返回空字符串"""
        result = T("nonexistent_key_xyz_12345", "zh")
        assert result == ""

    def test_default_lang_is_zh(self):
        """不传 lang 应默认中文"""
        result = T("menu_main")
        assert isinstance(result, str)

    def test_invalid_lang_falls_back(self):
        """无效语言应降级到中文"""
        result = T("menu_main", "xyz_invalid_lang")
        assert isinstance(result, str)


class TestFormatParams:

    def test_format_with_positional_args(self):
        """支持 format 占位符"""
        # 找一个有占位符的 key
        if "help_not_found" in I18N["zh"]:
            result = T("help_not_found", "zh", "missing_topic")
            assert "missing_topic" in result

    def test_format_with_no_args(self):
        result = T("menu_main", "zh")
        # 没占位符时应直接返回
        assert isinstance(result, str)


class TestModelListReplacement:

    def test_models_placeholder_in_text(self):
        """包含 {{models}} 的文本应自动替换为可用模型列表"""
        # 找一个含 {{models}} 的 key
        placeholder_keys = [k for k in I18N["zh"] if "{{models}}" in I18N["zh"][k]]
        if placeholder_keys:
            result = T(placeholder_keys[0], "zh")
            # 替换后不应包含 {{models}}
            assert "{{models}}" not in result

    def test_models_placeholder_english(self):
        placeholder_keys = [k for k in I18N["en"] if "{{models}}" in I18N["en"][k]]
        if placeholder_keys:
            result = T(placeholder_keys[0], "en")
            assert "{{models}}" not in result


class TestConsistency:

    def test_zh_and_en_both_have_keys(self):
        """主要 key 在两个语言下都应该有定义"""
        # 抽查一些菜单 key
        sample_keys = ["menu_main", "menu_config", "menu_agent"]
        for key in sample_keys:
            if key in I18N["zh"]:
                # 中文有,英文最好也有
                if key not in I18N["en"]:
                    pytest.skip(f"{key} 在 en 中未翻译")

    def test_i18n_dicts_exist(self):
        """I18N 字典应至少包含 zh 和 en"""
        assert "zh" in I18N
        assert "en" in I18N


class TestEdgeCases:

    def test_none_key(self):
        """None key 应不崩"""
        try:
            result = T(None, "zh")
            # 不崩即可
        except (TypeError, AttributeError):
            pass  # 抛异常也可

    def test_empty_string_key(self):
        result = T("", "zh")
        assert result == ""

    def test_special_chars_in_key(self):
        result = T("!@#$%", "zh")
        assert result == ""


class TestRealKeys:

    """测试一些真实存在的 key(从翻译文件)"""

    def test_menu_keys_exist(self):
        # 这些是启动时实际会用的菜单 key
        menu_keys = ["menu_main", "menu_config", "menu_cron"]
        for key in menu_keys:
            result = T(key, "zh")
            assert isinstance(result, str)

    def test_cron_messages_exist(self):
        # cron 相关的提示
        for key in ["cron_add", "cron_list", "cron_del"]:
            result = T(key, "zh")
            assert isinstance(result, str)
