"""
AI 页面分析 + 链接提取

让 LLM 分析 HTML 结构返回最优选择器，再选择合适提取方式（CSS / 正则）。
"""
import json
import re
from typing import List, Tuple
from urllib.parse import urljoin, urlparse


def _analyze_page_with_ai(html, url, state, failure_reason=None):
    """
    让 LLM 分析页面 HTML 结构，返回最优爬取策略。

    返回 dict:
        link_selector: CSS 选择器，用于提取正文链接
        content_selector: CSS 选择器，用于定位主要内容
        anti_bot_detected: bool
        advice: 绕过反爬的建议
        fetch_method: "requests" 或 "selenium"
        delay: 建议的延迟秒数
    """
    from fr_cli.core.stream import stream_cnt

    domain = urlparse(url).netloc
    html_snippet = html[:4000]

    failure_ctx = f"\n上次失败原因: {failure_reason}" if failure_reason else ""

    prompt = f"""你是一个专业的网页爬虫工程师。请分析以下网页的 HTML 结构，返回爬取策略。

要求输出严格 JSON 格式（不要 markdown 代码块）：
{{
    "link_selector": "提取正文/列表链接的 CSS 选择器，如 '.article-list a' 或 'article a'",
    "content_selector": "定位主要内容区域的 CSS 选择器，如 '.content' 或 'main'",
    "anti_bot_detected": true/false,
    "advice": "简短建议",
    "fetch_method": "requests 或 selenium",
    "delay": 建议的礼貌延迟秒数（1-5之间的数字）
}}

域名: {domain}
URL: {url}{failure_ctx}

HTML 片段:
```html
{html_snippet}
```

注意：
- link_selector 要尽量精准，避免导航栏/页脚/广告链接
- 如果页面是 JS 动态渲染，选择器可以留空，fetch_method 设为 selenium
- 只输出 JSON，不要其他文字。"""

    try:
        result_text, _, _, _ = stream_cnt(
            state.client, state.model_name,
            [{"role": "user", "content": prompt}],
            state.lang, custom_prefix="", max_tokens=512, silent=True
        )
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)

        strategy = json.loads(result_text)
        strategy.setdefault("link_selector", "")
        strategy.setdefault("content_selector", "")
        strategy.setdefault("anti_bot_detected", False)
        strategy.setdefault("advice", "")
        strategy.setdefault("fetch_method", "requests")
        strategy.setdefault("delay", 2.0)
        return strategy
    except Exception as e:
        return {
            "link_selector": "",
            "content_selector": "",
            "anti_bot_detected": False,
            "advice": f"AI 分析失败: {str(e)[:100]}，使用默认策略",
            "fetch_method": "requests",
            "delay": 2.0,
        }


def _extract_with_selector(html, selector, base_url) -> List[str]:
    """使用 CSS 选择器提取链接（需要 bs4）"""
    from fr_cli.agent.builtins.spider.deps import _get_bs4
    if not selector:
        return []
    bs4 = _get_bs4()
    if not bs4:
        return []

    try:
        soup = bs4(html, "html.parser")
        elements = soup.select(selector)
        links = set()
        base_domain = urlparse(base_url).netloc
        for el in elements:
            href = el.get("href")
            if href:
                full = urljoin(base_url, href)
                if urlparse(full).netloc == base_domain:
                    if not full.startswith(("javascript:", "mailto:", "tel:")):
                        links.add(full)
        return list(links)
    except Exception:
        return []


def _extract_links_regex(html, base_url) -> List[str]:
    """回退：使用正则提取链接"""
    links = set()
    base_domain = urlparse(base_url).netloc
    pattern = re.compile(r'href=["\']([^"\']+)["\']', re.I)
    for m in pattern.finditer(html):
        href = m.group(1)
        full = urljoin(base_url, href)
        if urlparse(full).netloc == base_domain:
            if not full.startswith(("javascript:", "mailto:", "tel:")):
                links.add(full)
    return list(links)


def _extract_links_smart(html, base_url, state, memory=None) -> Tuple[List[str], str]:
    """
    智能链接提取：先尝试记忆策略，失败则 AI 分析，再失败回退正则
    返回 (links, extraction_method)
    """
    from fr_cli.agent.builtins.spider.memory import (
        _get_domain_strategy,
        _update_domain_strategy_in_memory,
    )
    domain = urlparse(base_url).netloc
    strategy = _get_domain_strategy(domain, memory)

    # 1. 尝试记忆中的选择器
    if strategy and strategy.get("link_selector"):
        links = _extract_with_selector(html, strategy["link_selector"], base_url)
        if links:
            return links, "selector_memory"

    # 2. 无记忆或选择器失败 → 调用 AI 分析
    new_strategy = _analyze_page_with_ai(html, base_url, state)

    if new_strategy.get("link_selector"):
        links = _extract_with_selector(html, new_strategy["link_selector"], base_url)
        if links:
            _update_domain_strategy_in_memory(domain, new_strategy, success=True, memory=memory)
            return links, "selector_ai"
        else:
            _update_domain_strategy_in_memory(domain, new_strategy, success=False, memory=memory)

    # 3. 回退到正则
    links = _extract_links_regex(html, base_url)
    return links, "regex_fallback"
