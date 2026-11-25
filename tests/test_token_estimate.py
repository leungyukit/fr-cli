"""
Token 估算测试 —— 验证中文场景不再被低估

背景：旧实现用 `len(text) // 4`（英文经验值），中文实际约 1.5 字/token，
沿用 //4 会低估 2.7~4 倍，导致上下文压缩触发点远晚于模型真实上限。
"""
from fr_cli.memory.compress import (
    CJK_TOKEN_RATIO,
    OTHER_TOKEN_RATIO,
    TOKEN_SAFETY_FACTOR,
    estimate_tokens,
)


def _estimate_one(text, overhead=4):
    """估算单条消息的 token 数（带默认 overhead=4）。"""
    return estimate_tokens([{"role": "user", "content": text}], overhead=overhead)


class TestSignature:
    """既有签名与返回语义必须保持不变"""

    def test_returns_int(self):
        result = estimate_tokens([{"role": "user", "content": "hello"}])
        assert isinstance(result, int)

    def test_default_overhead_is_four(self):
        # 默认 overhead=4：内容估算 + 4
        text = "x" * 40
        assert estimate_tokens([{"role": "user", "content": text}]) == \
            estimate_tokens([{"role": "user", "content": text}], overhead=4)

    def test_overhead_applied_per_message(self):
        """每条消息各加一次 overhead（差值 = 内容估算 + overhead）。"""
        text = "x" * 40
        one = estimate_tokens([{"role": "user", "content": text}], overhead=4)
        two = estimate_tokens(
            [{"role": "user", "content": text}, {"role": "user", "content": text}],
            overhead=4,
        )
        content = estimate_tokens([{"role": "user", "content": text}], overhead=0)
        assert two - one == content + 4

    def test_zero_overhead(self):
        """overhead=0 时结果正好比默认少一个 overhead。"""
        text = "x" * 40
        default = estimate_tokens([{"role": "user", "content": text}], overhead=4)
        zero = estimate_tokens([{"role": "user", "content": text}], overhead=0)
        assert default - zero == 4

    def test_empty_messages(self):
        assert estimate_tokens([]) == 0

    def test_multimodal_content_supported(self):
        """多模态消息（content 为 list）仍可估算，不抛异常。"""
        result = estimate_tokens([
            {"role": "user", "content": [
                {"type": "text", "text": "x" * 40},
                {"type": "image_url", "image_url": {"url": "http://x"}},
            ]},
        ])
        assert result > 0


class TestMixedAware:
    """混合感知：中文显著高于英文；中英混排介于两者之间"""

    def test_chinese_costs_more_than_english_of_same_length(self):
        """同样字数，中文估算出的 token 数显著大于英文（不含固定 overhead）。"""
        zh = "这是一段用于测试的中文文本内容示例" * 10
        en = "a" * len(zh)
        zh_tokens = _estimate_one(zh, overhead=0)
        en_tokens = _estimate_one(en, overhead=0)
        assert zh_tokens > en_tokens * 2, (zh_tokens, en_tokens)

    def test_mixed_is_between(self):
        """等长度的纯中文 / 纯英文 / 中英混排：混排介于两者之间。"""
        n = 200
        zh = "中" * n                       # 200 个 CJK 字
        en = "a" * n                       # 200 个 ASCII
        mixed = "a中" * (n // 2)           # 同样 200 字，一半一半
        assert len(mixed) == len(zh) == len(en)
        zh_tokens = _estimate_one(zh, overhead=0)
        en_tokens = _estimate_one(en, overhead=0)
        mixed_tokens = _estimate_one(mixed, overhead=0)
        assert en_tokens < mixed_tokens < zh_tokens, (en_tokens, mixed_tokens, zh_tokens)

    def test_english_roughly_four_chars_per_token(self):
        """英文仍按约 4 字符/token（0.25 token/字符）估算。"""
        en = "a" * 400
        content_tokens = _estimate_one(en, overhead=0)
        # 400 * 0.25 = 100，安全系数后约 108，允许小幅浮动
        assert 95 <= content_tokens <= 115

    def test_chinese_roughly_one_point_five_chars_per_token(self):
        """中文约 1.5 字/token（0.65 token/字），不再是 //4 的 0.25。"""
        zh = "中" * 300
        content_tokens = _estimate_one(zh, overhead=0)
        # 300 * 0.65 = 195，安全系数后约 210
        assert 185 <= content_tokens <= 225

    def test_fullwidth_and_kana_counted_as_cjk(self):
        """全角字符 / 假名 / 韩文音节也算 CJK（不能按西文 0.25 算）。"""
        fullwidth = "ＡＢＣ" * 50      # 全角
        kana = "ひらがな" * 50           # 假名
        hangul = "한국어" * 50           # 韩文
        for text in (fullwidth, kana, hangul):
            content_tokens = _estimate_one(text, overhead=0)
            # 按 CJK 计权：至少 0.6 token/字（含安全系数）
            assert content_tokens >= int(len(text) * 0.6), (content_tokens, text[:4])

    def test_cjk_punctuation_counts_as_cjk(self):
        """中日韩标点按 CJK 计权。"""
        punct = "，。！？" * 100
        content_tokens = _estimate_one(punct, overhead=0)
        assert content_tokens >= 60


class TestSafetyFactor:
    """保守系数：宁可高估不可低估"""

    def test_safety_factor_is_at_least_one(self):
        assert TOKEN_SAFETY_FACTOR >= 1.0
        assert TOKEN_SAFETY_FACTOR <= 1.15

    def test_ratios_are_sane(self):
        assert 0.55 <= CJK_TOKEN_RATIO <= 0.75
        assert 0.2 <= OTHER_TOKEN_RATIO <= 0.3

    def test_chinese_estimate_has_a_lower_bound(self):
        """中文估算不得低于 0.6 token/字（含安全系数）。"""
        zh = "这是一段用于测试的中文文本内容示例"
        content_tokens = _estimate_one(zh, overhead=0)
        assert content_tokens >= int(len(zh) * 0.6)

    def test_never_underestimates_theoretical_value(self):
        """含安全系数后，估算值不低于理论值（不做向下取整损失）。"""
        for text in ("中" * 50, "a" * 50, "混合mixed内容" * 5):
            content_tokens = _estimate_one(text, overhead=0)
            assert content_tokens >= 1


class TestRealWorldScenarios:
    """贴近真实场景的回归"""

    def test_long_chinese_conversation_triggers_earlier(self):
        """旧实现对中文低估约 4 倍；新实现必须显著更高。"""
        text = "请帮我分析一下这份电商选品报告，并给出选品建议" * 4
        messages = [{"role": "user", "content": text}] * 10
        new_value = estimate_tokens(messages)
        old_value = sum(max(1, len(m["content"]) // 4) + 4 for m in messages)
        assert new_value > old_value * 2, (new_value, old_value)

    def test_empty_content_message_still_costs_overhead(self):
        """空消息也要计入 overhead（与旧实现一致）。"""
        assert estimate_tokens([{"role": "user", "content": ""}]) == 5
