"""
@spider 内置 Agent —— 智能网页爬虫助手
模拟真人浏览行为，支持反爬自适应，使用 requests → selenium 降级策略。
"""
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

# 尝试导入可选依赖
_requests = None
_selenium = None


def _get_requests():
    global _requests
    if _requests is None:
        try:
            import requests as r
            _requests = r
        except ImportError:
            pass
    return _requests


def _get_selenium():
    global _selenium
    if _selenium is None:
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            _selenium = {"webdriver": webdriver, "By": By, "ActionChains": ActionChains}
        except ImportError:
            pass
    return _selenium


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


def _sanitize_filename(url):
    """将 URL 转换为安全的文件名"""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_")
    if not path:
        path = "index"
    name = f"{parsed.netloc}_{path}"
    name = re.sub(r'[^\w\-_]', '_', name)[:100]
    return name + ".html"


def _fetch_with_requests(url):
    """使用 requests 获取页面"""
    requests = _get_requests()
    if not requests:
        return None, "requests 未安装 (pip install requests)"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text
        # 简单反爬检测
        if len(text) < 500 or "captcha" in text.lower() or "access denied" in text.lower():
            return None, "可能触发反爬机制"
        return text, None
    except Exception as e:
        return None, str(e)


def _fetch_with_selenium(url):
    """使用 selenium 模拟真人浏览"""
    sel = _get_selenium()
    if not sel:
        return None, "selenium 未安装 (pip install selenium)"

    webdriver = sel["webdriver"]
    By = sel["By"]
    ActionChains = sel["ActionChains"]

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        # 模拟真人行为
        time.sleep(random.uniform(1.5, 3.0))

        # 随机滚动
        for _ in range(random.randint(2, 5)):
            scroll_y = random.randint(100, 800)
            driver.execute_script(f"window.scrollBy(0, {scroll_y});")
            time.sleep(random.uniform(0.5, 1.5))

        # 随机悬停
        try:
            elements = driver.find_elements(By.TAG_NAME, "a")
            if elements:
                el = random.choice(elements[:10])
                ActionChains(driver).move_to_element(el).pause(random.uniform(0.3, 0.8)).perform()
        except Exception:
            pass

        # 再滚动回顶部
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(random.uniform(0.5, 1.0))

        html = driver.page_source
        return html, None
    except Exception as e:
        return None, str(e)
    finally:
        if driver:
            driver.quit()


def _extract_links(html, base_url):
    """从 HTML 中提取同域名链接"""
    links = set()
    base_domain = urlparse(base_url).netloc
    pattern = re.compile(r'href=["\']([^"\']+)["\']', re.I)
    for m in pattern.finditer(html):
        href = m.group(1)
        full = urljoin(base_url, href)
        if urlparse(full).netloc == base_domain:
            # 去重和过滤
            if not full.startswith("javascript:") and not full.startswith("mailto:"):
                links.add(full)
    return list(links)


def _save_page(url, html, output_dir):
    """保存页面到工作区"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(url)
    filepath = output_dir / filename
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)


def crawl(url, depth=1, output_base=None, lang="zh"):
    """爬取指定 URL，返回 (saved_files, errors)"""
    from fr_cli.ui.ui import CYAN, GREEN, RED, DIM, YELLOW, RESET

    if depth < 1:
        depth = 1
    if depth > 3:
        depth = 3  # 限制最大深度为 3

    if output_base is None:
        output_base = Path.cwd() / f"web_{datetime.now().strftime('%Y%m%d')}"
    else:
        output_base = Path(output_base)

    saved = []
    errors = []
    visited = set()
    to_crawl = [(url, 0)]  # (url, current_depth)

    while to_crawl:
        current_url, current_depth = to_crawl.pop(0)
        if current_url in visited or current_depth >= depth:
            continue
        visited.add(current_url)

        print(f"{CYAN}🕷️ 爬取 [{current_depth+1}/{depth}]: {current_url[:80]}...{RESET}")

        # 第一优先级: requests
        html, err = _fetch_with_requests(current_url)
        if err or not html:
            print(f"{YELLOW}  requests 失败: {err or '内容为空'}，尝试 selenium...{RESET}")
            html, err2 = _fetch_with_selenium(current_url)
            if err2 or not html:
                errors.append(f"{current_url}: {err2 or err}")
                print(f"{RED}  ❌ 爬取失败: {err2 or err}{RESET}")
                continue

        # 保存页面
        filepath = _save_page(current_url, html, output_base)
        saved.append(filepath)
        print(f"{GREEN}  ✅ 已保存: {filepath}{RESET}")

        # 如果还有深度，提取链接继续爬
        if current_depth + 1 < depth:
            links = _extract_links(html, current_url)
            for link in links[:20]:  # 每页最多20个链接
                if link not in visited:
                    to_crawl.append((link, current_depth + 1))
            if links:
                print(f"{DIM}  发现 {len(links)} 个链接，加入 {min(len(links), 20)} 个待爬取{RESET}")

        # 礼貌延迟
        time.sleep(random.uniform(1.0, 2.5))

    return saved, errors


def handle_spider(user_input, state):
    """处理 @spider 前缀的请求"""
    from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET

    text = user_input[len("@spider"):].strip()
    if not text:
        print(f"{RED}用法: @spider <URL> [深度]{RESET}")
        return

    parts = text.split()
    url = parts[0]
    depth = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    if not url.startswith("http"):
        url = "https://" + url

    # 检查依赖
    if not _get_requests():
        print(f"{RED}缺少依赖: pip install requests selenium{RESET}")
        return

    output_dir = None
    if state.vfs and state.vfs.cwd:
        output_dir = state.vfs.cwd

    print(f"{CYAN}🕷️ 开始爬取: {url} | 深度: {depth}{RESET}")
    saved, errors = crawl(url, depth, output_dir, state.lang)

    print(f"\n{GREEN}═══ 爬取完成 ═══{RESET}")
    print(f"{GREEN}  成功: {len(saved)} 个页面{RESET}")
    if errors:
        print(f"{RED}  失败: {len(errors)} 个页面{RESET}")
        for e in errors[:5]:
            print(f"{RED}    - {e}{RESET}")
    if saved:
        print(f"{DIM}  保存目录: {Path(saved[0]).parent}{RESET}")
