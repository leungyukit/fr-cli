"""
@spider 自适应页面获取 —— requests / selenium 自动降级

_fetch_adaptive 根据域名记忆选择最佳获取方式；requests 模式优先，
触发反爬特征时自动降级到 selenium 模拟真人浏览。
"""
import random
from pathlib import Path
from typing import Optional, Tuple

from fr_cli.agent.builtins.spider.deps import (
    USER_AGENTS,
    _get_requests,
    _get_requests_session,
    _get_selenium,
    _get_undetected_chromedriver,
    _WINDOW_SIZES,
)
from fr_cli.agent.builtins.spider.evasion import (
    _build_fingerprint_evasion_script,
    _simulate_human_scrolling,
    _simulate_mouse_movement,
    _simulate_random_clicks,
    _simulate_reading_pauses,
)
from fr_cli.agent.builtins.spider.memory import (
    _get_domain_strategy,
    _sanitize_filename,
    _update_domain_strategy_in_memory,
)


def _fetch_adaptive(url, state, memory=None, force_selenium=False):
    """
    自适应获取页面：根据域名记忆选择最佳获取方式
    返回 (html, err, method_used)
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    strategy = _get_domain_strategy(domain, memory)

    use_selenium = force_selenium
    if strategy and strategy.get("fetch_method") == "selenium":
        use_selenium = True

    delay = strategy.get("delay", 2.0) if strategy else random.uniform(1.0, 2.5)
    if delay < 0.5:
        delay = 1.0
    if delay > 5:
        delay = 5.0

    if not use_selenium:
        html, err = _fetch_with_requests(url)
        if html and not err:
            if len(html) < 500 or "captcha" in html.lower() or "access denied" in html.lower():
                err = "可能触发反爬机制"
            else:
                if strategy:
                    _update_domain_strategy_in_memory(domain, {"fetch_method": "requests"}, success=True, memory=memory)
                return html, None, "requests"

        print(f"  requests 失败: {err or '内容为空'}，尝试 selenium...")
        use_selenium = True

    if use_selenium:
        html, err = _fetch_with_selenium(url)
        if html and not err:
            _update_domain_strategy_in_memory(domain, {
                "fetch_method": "selenium",
                "delay": delay,
            }, success=True, memory=memory)
            return html, None, "selenium"
        else:
            _update_domain_strategy_in_memory(domain, {
                "fetch_method": "selenium",
                "delay": delay + 1.0,
            }, success=False, memory=memory)
            return None, err or "selenium 获取失败", "selenium"

    return None, "所有获取方式均失败", "none"


def _fetch_with_requests(url) -> Tuple[Optional[str], Optional[str]]:
    """使用 requests Session 获取页面，模拟完整浏览器指纹"""
    import time
    requests = _get_requests()
    if not requests:
        return None, "requests 未安装 (pip install requests)"

    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    session = _get_requests_session(domain)
    if not session:
        return None, "requests 初始化失败"

    # 完整浏览器请求头，模拟真实 Chrome
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": random.choice([
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "en-US,en;q=0.9,zh-CN;q=0.8",
        ]),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "DNT": "1",
        "Cache-Control": random.choice(["max-age=0", "no-cache"]),
    }

    # Referer：模拟从搜索引擎或首页进入
    referers = [
        f"https://www.google.com/search?q={domain}",
        f"https://www.bing.com/search?q={domain}",
        f"https://{domain}/",
    ]
    headers["Referer"] = random.choice(referers)

    try:
        resp = session.get(url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        text = resp.text

        # 反爬检测（更全面的关键词）
        anti_bot_signals = [
            "captcha", "access denied", "blocked", "forbidden",
            "cloudflare", "checking your browser", "ddos-guard",
            "pleasewait", " verifying ", "自动化", "机器人",
        ]
        lower_text = text.lower()
        if len(text) < 500 or any(s in lower_text for s in anti_bot_signals):
            return None, "可能触发反爬机制"
        return text, None
    except Exception as e:
        return None, str(e)


def _fetch_with_selenium(url) -> Tuple[Optional[str], Optional[str]]:
    """使用 selenium / undetected-chromedriver 完全模拟真人浏览"""
    import time
    sel = _get_selenium()
    if not sel:
        return None, "selenium 未安装 (pip install selenium)"

    uc = _get_undetected_chromedriver()
    webdriver = sel["webdriver"]
    By = sel["By"]
    use_uc = uc is not None

    # 随机窗口大小（避免固定 1920x1080）
    width, height = random.choice(_WINDOW_SIZES)

    driver = None
    try:
        if use_uc:
            # ========== undetected-chromedriver 模式（更强的反检测）==========
            options = uc.ChromeOptions()
            options.headless = True
            options.add_argument(f"--window-size={width},{height}")
            options.add_argument("--disable-webgl")
            options.add_argument("--disable-3d-apis")
            options.add_argument("--timezone=Asia/Shanghai")
            # uc 已经自动处理了：navigator.webdriver、CDC、chrome.runtime 等
            driver = uc.Chrome(options=options)
        else:
            # ========== 标准 selenium 模式（手动注入规避脚本）==========
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
            options.add_argument(f"--window-size={width},{height}")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("--disable-webgl")
            options.add_argument("--disable-3d-apis")
            options.add_argument("--timezone=Asia/Shanghai")

            driver = webdriver.Chrome(options=options)

            # 注入完整的指纹规避脚本
            evasion_script = _build_fingerprint_evasion_script()
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': evasion_script
            })

            # 清除 Chrome Driver 的 CDC 特征
            driver.execute_cdp_cmd('Runtime.evaluate', {
                'expression': '''
                    let objectToInspect = window;
                    let result = [];
                    while (objectToInspect !== null) {
                        result = result.concat(Object.getOwnPropertyNames(objectToInspect));
                        objectToInspect = Object.getPrototypeOf(objectToInspect);
                    }
                    for (let i = 0; i < result.length; i++) {
                        if (result[i].indexOf('cdc_') > -1 || result[i].indexOf('chrome') > -1 && result[i].indexOf('cdc') > -1) {
                            let val = window[result[i]];
                            if (val && typeof val === 'object') {
                                Object.defineProperty(window, result[i], { get: () => undefined });
                            }
                        }
                    }
                '''
            })

        # 访问页面
        driver.get(url)

        # 初始加载等待（模拟人类首次访问的耐心）
        time.sleep(random.uniform(2.5, 5.0))

        # 执行完整的人类行为模拟
        _simulate_human_scrolling(driver)
        _simulate_reading_pauses(driver)
        _simulate_random_clicks(driver)

        # 偶尔模拟鼠标移动到某个元素上（使用贝塞尔曲线）
        try:
            elements = driver.find_elements(By.TAG_NAME, "a")
            if elements:
                el = random.choice(elements[:8])
                loc = el.location
                size = el.size
                if loc and size:
                    target_x = loc['x'] + size['width'] / 2
                    target_y = loc['y'] + size['height'] / 2
                    start_x = random.randint(100, 400)
                    start_y = random.randint(100, 400)
                    _simulate_mouse_movement(driver, start_x, start_y, target_x, target_y)
        except Exception:
            pass

        html = driver.page_source
        return html, None
    except Exception as e:
        return None, str(e)
    finally:
        if driver:
            driver.quit()


def _save_page(url: str, html: str, output_dir) -> str:
    """保存页面到工作区"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(url)
    filepath = output_dir / filename
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)