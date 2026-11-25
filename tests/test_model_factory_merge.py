"""
ModelFactory 合并语义回归测试

背景：~/.fr_cli/models.yaml 是用户覆盖文件，旧实现是“用户文件整体替换内置
default_models.yaml”。用户文件只写了 3 个 provider 时，会把内置 26 个厂商
目录整个遮蔽掉，/model list 只剩 3 个可选。

现改为“内置目录为底座 + 用户文件覆盖合并”（用户字段优先、内置补缺），
并顺带把旧 schema 字段名（protocol 等）升级到当前 schema。
"""
import json


from fr_cli.core.model_factory import ModelFactory


def _factory_with(tmp_path, text, name="models.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return ModelFactory().load_config(p)


class TestMergeWithBuiltin:
    """用户文件不再整体遮蔽内置厂商目录"""

    def test_partial_user_file_keeps_builtin(self, tmp_path):
        """用户只写 1 个 provider 时，内置目录全部保留"""
        f = _factory_with(tmp_path, "my_provider:\n  name: 自建\n  model: m1\n")
        assert "my_provider" in f._config
        # 内置代表性厂商都还在
        for pid in ("zhipu", "openai", "deepseek", "minimax", "kimi", "ollama"):
            assert pid in f._config, f"内置 provider {pid} 被遮蔽了"

    def test_builtin_count_preserved_when_user_empty(self, tmp_path):
        """空用户文件 → 纯内置目录（= default_models.yaml 条目数）"""
        f = _factory_with(tmp_path, "")
        builtin = ModelFactory()._get_default_config()
        assert len(f._config) == len(builtin)

    def test_user_only_provider_appended(self, tmp_path):
        """用户独有 provider（不在内置目录）被原样并入"""
        f = _factory_with(
            tmp_path,
            "volcengine-plan:\n"
            "  name: volcengine-coding-plan\n"
            "  model: ark-code-latest\n"
            "  base_url: https://ark.cn-beijing.volces.com/api/coding/v3\n"
            "  compat: openai\n",
        )
        assert "volcengine-plan" in f._config
        assert f._config["volcengine-plan"]["model"] == "ark-code-latest"
        assert f._config["volcengine-plan"]["base_url"].endswith("/api/coding/v3")

    def test_missing_file_falls_back_to_builtin(self, tmp_path):
        """文件不存在 → 纯内置目录"""
        f = ModelFactory().load_config(tmp_path / "nonexistent.yaml")
        builtin = ModelFactory()._get_default_config()
        assert len(f._config) == len(builtin)

    def test_empty_file_falls_back_to_builtin(self, tmp_path):
        """空文件 → 纯内置目录"""
        f = _factory_with(tmp_path, "")
        builtin = ModelFactory()._get_default_config()
        assert len(f._config) == len(builtin)

    def test_corrupt_file_falls_back_to_builtin(self, tmp_path):
        """损坏文件 → 纯内置目录，不抛异常"""
        f = _factory_with(tmp_path, ":::not yaml{[")
        builtin = ModelFactory()._get_default_config()
        assert len(f._config) == len(builtin)

    def test_non_dict_content_falls_back_to_builtin(self, tmp_path):
        """顶层是 list 而非 dict → 纯内置目录"""
        f = _factory_with(tmp_path, "- a\n- b\n")
        builtin = ModelFactory()._get_default_config()
        assert len(f._config) == len(builtin)


class TestUserFieldPriority:
    """用户字段优先，内置字段补缺"""

    def test_user_base_url_wins_and_builtin_fills_gap(self, tmp_path):
        """用户自定义 base_url 保留，同时补上内置的 models 列表"""
        f = _factory_with(
            tmp_path,
            "deepseek:\n"
            "  name: DeepSeek\n"
            "  model: deepseek-chat\n"
            "  base_url: https://api.deepseek.com/v1\n",
        )
        # 用户的定制保留
        assert f._config["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
        # 内置缺失的字段补上
        assert f._config["deepseek"]["models"] == [
            "deepseek-chat", "deepseek-reasoner", "deepseek-coder",
        ]
        assert f._config["deepseek"]["compat"] == "openai"

    def test_user_model_override_wins(self, tmp_path):
        """用户改 default model 时以用户为准"""
        f = _factory_with(tmp_path, "deepseek:\n  model: deepseek-reasoner\n")
        assert f._config["deepseek"]["model"] == "deepseek-reasoner"

    def test_user_name_override_wins(self, tmp_path):
        """用户自定义 name 时以用户为准"""
        f = _factory_with(tmp_path, "kimi-code:\n  name: kimi-code\n")
        assert f._config["kimi-code"]["name"] == "kimi-code"


class TestLegacySchemaUpgrade:
    """旧 schema 字段名升级为当前 schema"""

    def test_protocol_upgraded_to_compat(self, tmp_path):
        """protocol(旧) → compat(新)"""
        f = _factory_with(tmp_path, "my_provider:\n  model: m1\n  protocol: openai\n")
        assert f._config["my_provider"]["compat"] == "openai"

    def test_explicit_compat_not_overwritten(self, tmp_path):
        """已有 compat 时不被 protocol 覆盖"""
        f = _factory_with(
            tmp_path, "my_provider:\n  model: m1\n  compat: anthropic\n  protocol: openai\n"
        )
        assert f._config["my_provider"]["compat"] == "anthropic"

    def test_upgrade_is_idempotent(self, tmp_path):
        """重复 load_config 结果一致（幂等）"""
        text = "my_provider:\n  model: m1\n  protocol: openai\n"
        f1 = _factory_with(tmp_path, text)
        f2 = _factory_with(tmp_path, text)
        assert f1._config == f2._config


class TestLegacyNestedFormat:
    """旧版嵌套 providers: 格式解包"""

    def test_nested_providers_unwrapped(self, tmp_path):
        """providers: 包裹时解包为扁平 provider 字典"""
        f = _factory_with(
            tmp_path,
            "providers:\n"
            "  deepseek:\n"
            "    name: DeepSeek\n"
            "    model: deepseek-chat\n"
            "    protocol: openai\n"
            "    base_url: https://api.deepseek.com/v1\n",
        )
        assert "providers" not in f._config
        assert "deepseek" in f._config
        assert f._config["deepseek"]["base_url"] == "https://api.deepseek.com/v1"

    def test_settings_key_not_treated_as_provider(self, tmp_path):
        """settings 段不能被当成一个 provider"""
        f = _factory_with(
            tmp_path,
            "providers:\n"
            "  deepseek:\n    model: deepseek-chat\n"
            "settings:\n"
            "  default_provider: deepseek\n"
            "  history_window: 5\n",
        )
        assert "settings" not in f._config
        assert "deepseek" in f._config

    def test_flat_file_with_stray_settings_key(self, tmp_path):
        """扁平格式里混入 settings 键也要跳过"""
        f = _factory_with(
            tmp_path,
            "deepseek:\n  model: deepseek-chat\n"
            "settings:\n  default_provider: deepseek\n",
        )
        assert "settings" not in f._config

    def test_non_dict_entry_skipped(self, tmp_path):
        """值不是 dict 的条目被跳过，不当成 provider"""
        f = _factory_with(
            tmp_path,
            "deepseek:\n  model: deepseek-chat\n"
            "broken_entry: just-a-string\n",
        )
        assert "broken_entry" not in f._config
        assert "deepseek" in f._config


class TestRealisticUserFile:
    """贴近真实场景：用户旧文件 3 个 provider，其中 1 个自建"""

    def test_three_provider_user_file_yields_full_catalog(self, tmp_path):
        """旧嵌套格式 3 个 provider → 内置全量 + 自建 provider"""
        f = _factory_with(
            tmp_path,
            "providers:\n"
            "  deepseek:\n"
            "    name: DeepSeek\n"
            "    model: deepseek-chat\n"
            "    protocol: openai\n"
            "    base_url: https://api.deepseek.com/v1\n"
            "  kimi-code:\n"
            "    name: kimi-code\n"
            "    model: kimi-for-coding\n"
            "    protocol: openai\n"
            "    base_url: https://api.kimi.com/coding/v1\n"
            "  volcengine-plan:\n"
            "    name: volcengine-coding-plan\n"
            "    model: ark-code-latest\n"
            "    protocol: openai\n"
            "    base_url: https://ark.cn-beijing.volces.com/api/coding/v3\n"
            "settings:\n"
            "  default_provider: volcengine-plan\n",
        )
        builtin = ModelFactory()._get_default_config()
        # 内置全量 + 1 个自建
        assert len(f._config) == len(builtin) + 1
        assert set(builtin) <= set(f._config)
        assert "volcengine-plan" in f._config
        assert "settings" not in f._config
        # 用户定制未丢
        assert f._config["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
        assert f._config["volcengine-plan"]["base_url"].endswith("/api/coding/v3")


class TestSuffixHandling:
    """str / Path 与 .json 后缀的兼容（既有行为不能被合并改动破坏）"""

    def test_json_suffix_user_file(self, tmp_path):
        """.json 用户文件也参与合并"""
        p = tmp_path / "models.json"
        p.write_text(json.dumps({"json_provider": {"model": "json-model"}}), encoding="utf-8")
        f = ModelFactory().load_config(p)
        assert f._config["json_provider"]["model"] == "json-model"
        assert "openai" in f._config

    def test_string_path_accepted(self, tmp_path):
        """config_path 传 str 也工作"""
        p = tmp_path / "models.yaml"
        p.write_text("str_provider:\n  model: str-model\n", encoding="utf-8")
        f = ModelFactory().load_config(str(p))
        assert "str_provider" in f._config

    def test_no_endswith_warning(self, tmp_path, recwarn):
        """默认路径加载不产生 PosixPath/endswith 警告"""
        p = tmp_path / "models.yaml"
        p.write_text("x:\n  model: m\n", encoding="utf-8")
        ModelFactory().load_config(p)
        warnings = [w for w in recwarn.list
                    if "endswith" in str(w.message).lower()
                    or "PosixPath" in str(w.message)]
        assert not warnings
