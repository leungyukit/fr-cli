"""
@spider 主爬取逻辑 —— crawl / 反思进化 / REPL 入口
"""
import json
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fr_cli.core.result import Result

from fr_cli.agent.builtins.spider.analyzer import _extract_links_smart
from fr_cli.agent.builtins.spider.deps import _get_requests
from fr_cli.agent.builtins.spider.fetcher import _fetch_adaptive, _save_page
from fr_cli.agent.builtins.spider.memory import (
    SPIDER_EVOLUTION_FILE,
    _ensure_spider_memory_dir,
    _get_domain_strategy,
    _load_spider_memory,
    _save_spider_memory,
)


def crawl(url, depth=1, output_base=None, lang="zh", state=None):
    """自适应爬取指定 URL，返回 (saved_files, errors, stats)"""
    from fr_cli.ui.ui import CYAN, GREEN, RED, DIM, RESET

    if depth < 1:
        depth = 1
    if depth > 3:
        depth = 3

    if output_base is None:
        output_base = Path.cwd() / f"web_{datetime.now().strftime('%Y%m%d')}"
    else:
        output_base = Path(output_base)

    saved = []
    errors = []
    visited = set()
    to_crawl = [(url, 0)]

    memory = _load_spider_memory()

    stats = {
        "total_pages": 0,
        "success_requests": 0,
        "success_selenium": 0,
        "selector_memory_hits": 0,
        "selector_ai_hits": 0,
        "regex_fallbacks": 0,
        "domains": set(),
    }

    while to_crawl:
        current_url, current_depth = to_crawl.pop(0)
        if current_url in visited or current_depth >= depth:
            continue
        visited.add(current_url)
        stats["total_pages"] += 1
        stats["domains"].add(urlparse(current_url).netloc)

        print(f"{CYAN}🕷️ 爬取 [{current_depth+1}/{depth}]: {current_url[:80]}...{RESET}")

        html, err, method = _fetch_adaptive(current_url, state, memory=memory)
        if err or not html:
            errors.append(f"{current_url}: {err}")
            print(f"{RED}  ❌ 爬取失败: {err}{RESET}")
            continue

        if method == "requests":
            stats["success_requests"] += 1
        elif method == "selenium":
            stats["success_selenium"] += 1

        filepath = _save_page(current_url, html, output_base)
        saved.append(filepath)
        print(f"{GREEN}  ✅ 已保存: {filepath} (via {method}){RESET}")

        if current_depth + 1 < depth:
            links, extraction_method = _extract_links_smart(html, current_url, state, memory=memory)

            if extraction_method == "selector_memory":
                stats["selector_memory_hits"] += 1
            elif extraction_method == "selector_ai":
                stats["selector_ai_hits"] += 1
            else:
                stats["regex_fallbacks"] += 1

            for link in links[:20]:
                if link not in visited:
                    to_crawl.append((link, current_depth + 1))
            if links:
                print(f"{DIM}  发现 {len(links)} 个链接（{extraction_method}），加入 {min(len(links), 20)} 个待爬取{RESET}")

        domain = urlparse(current_url).netloc
        strategy = _get_domain_strategy(domain, memory)
        delay = strategy.get("delay", random.uniform(1.0, 2.5)) if strategy else random.uniform(1.0, 2.5)
        time.sleep(delay)

    # 统一保存记忆
    _save_spider_memory(memory)

    # 爬取结束后：AI 反思进化
    if state and (stats["total_pages"] >= 2 or errors):
        _reflect_and_evolve(stats, errors, memory, state)

    return Result.ok((saved, errors, stats))


def _reflect_and_evolve(stats, errors, memory, state):
    """爬取结束后让 AI 反思，生成进化建议并保存。"""
    from fr_cli.core.stream import stream_cnt

    domains_summary = []
    for domain, data in memory.items():
        domains_summary.append(
            f"- {domain}: 成功率 {data.get('success_rate', 0):.0%}, "
            f"推荐方式 {data.get('fetch_method', 'unknown')}, "
            f"选择器 {data.get('link_selector', 'none') or 'none'}"
        )

    error_summary = "\n".join(errors[:5]) if errors else "无"

    prompt = f"""作为爬虫工程师，请基于本次爬取数据生成优化建议。

爬取统计：
- 总页面: {stats['total_pages']}
- requests 成功: {stats['success_requests']}
- selenium 成功: {stats['success_selenium']}
- 选择器记忆命中: {stats['selector_memory_hits']}
- AI 选择器生成: {stats['selector_ai_hits']}
- 正则回退: {stats['regex_fallbacks']}

域名策略记录：
{chr(10).join(domains_summary[:10])}

失败案例：
{error_summary}

请输出简洁的优化建议（不超过200字），我将保存到爬虫进化记录中。"""

    try:
        advice, _, _, _ = stream_cnt(
            state.client, state.model_name,
            [{"role": "user", "content": prompt}],
            state.lang, custom_prefix="", max_tokens=256, silent=True
        )
        advice = advice.strip()
        if advice:
            _ensure_spider_memory_dir()
            evolution = {}
            if SPIDER_EVOLUTION_FILE.exists():
                try:
                    with open(SPIDER_EVOLUTION_FILE, "r", encoding="utf-8") as f:
                        evolution = json.load(f)
                except Exception:
                    pass
            evolution["last_advice"] = advice
            evolution["last_updated"] = datetime.now().isoformat()
            evolution["total_crawls"] = evolution.get("total_crawls", 0) + 1
            with open(SPIDER_EVOLUTION_FILE, "w", encoding="utf-8") as f:
                json.dump(evolution, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def handle_spider(user_input, state):
    """处理 @spider 前缀的请求"""
    from fr_cli.ui.ui import CYAN, GREEN, RED, DIM, RESET

    text = user_input[len("@spider"):].strip()
    if not text:
        print(f"{RED}用法: @spider <URL> [深度]{RESET}")
        return

    parts = text.split()
    url = parts[0]
    depth = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    if not url.startswith("http"):
        url = "https://" + url

    if not _get_requests():
        print(f"{RED}缺少依赖: pip install requests{RESET}")
        return

    output_dir = None
    if state.vfs and state.vfs.cwd:
        output_dir = state.vfs.cwd

    print(f"{CYAN}🕷️ 开始自适应爬取: {url} | 深度: {depth}{RESET}")
    print(f"{DIM}  爬虫会根据页面结构自动分析最优策略...{RESET}")

    saved, errors, stats = crawl(url, depth, output_dir, state.lang, state=state).unwrap()

    print(f"\n{GREEN}═══ 爬取完成 ═══{RESET}")
    print(f"{GREEN}  成功: {len(saved)} 个页面{RESET}")
    if stats["success_selenium"] > 0:
        print(f"{DIM}  selenium 渲染: {stats['success_selenium']} 页{RESET}")
    if stats["selector_ai_hits"] > 0:
        print(f"{DIM}  AI 动态分析: {stats['selector_ai_hits']} 次{RESET}")
    if stats["selector_memory_hits"] > 0:
        print(f"{DIM}  记忆策略命中: {stats['selector_memory_hits']} 次{RESET}")
    if errors:
        print(f"{RED}  失败: {len(errors)} 个页面{RESET}")
        for e in errors[:5]:
            print(f"{RED}    - {e}{RESET}")
    if saved:
        print(f"{DIM}  保存目录: {Path(saved[0]).parent}{RESET}")

    if SPIDER_EVOLUTION_FILE.exists():
        try:
            with open(SPIDER_EVOLUTION_FILE, "r", encoding="utf-8") as f:
                evo = json.load(f)
            if evo.get("last_advice"):
                print(f"{DIM}  最新进化: {evo['last_advice'][:80]}...{RESET}")
        except Exception:
            pass