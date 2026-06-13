"""
@spider 内置 Agent —— 自适应智能网页爬虫助手

核心能力：
1. AI 动态分析页面结构，生成最优 CSS 选择器
2. 域名级记忆系统，记录成功/失败策略
3. requests → selenium 自适应降级
4. 爬取结束后自动反思进化
"""
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from fr_cli.core.result import Result

# 尝试导入可选依赖
_requests = None
_selenium = None
_bs4 = None


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


def _get_undetected_chromedriver():
    """尝试导入 undetected-chromedriver（更强的反检测能力）"""
    try:
        import undetected_chromedriver as uc
        return uc
    except ImportError:
        return None


def _get_bs4():
    global _bs4
    if _bs4 is None:
        try:
            from bs4 import BeautifulSoup
            _bs4 = BeautifulSoup
        except ImportError:
            pass
    return _bs4


# ---------- 用户代理池 ----------
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# 常见真实窗口分辨率（避免只用 1920x1080）
_WINDOW_SIZES = [
    (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
    (1280, 720), (1600, 900), (1680, 1050), (2560, 1440),
]

# requests Session 池（保持 Cookie 连续性）
_requests_sessions = {}


def _get_requests_session(domain: str):
    """获取带 Cookie 持久化的 Session，每个域名独立"""
    global _requests_sessions
    if domain not in _requests_sessions:
        requests = _get_requests()
        if not requests:
            return None
        _requests_sessions[domain] = requests.Session()
    return _requests_sessions[domain]


# ---------- 人类行为模拟 ----------

def _bezier_curve(p0, p1, p2, t):
    """二次贝塞尔曲线：返回 t 时刻的坐标"""
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
    return x, y


def _build_fingerprint_evasion_script():
    """构建浏览器指纹规避 JS 脚本，注入到每个新页面"""
    return """
    // 1. 隐藏 webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // 2. 模拟 window.chrome
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {},
    };

    // 3. 模拟 plugins（Chrome 通常有 3 个内置插件）
    Object.defineProperty(navigator, 'plugins', {
        get: function() {
            return [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: 'Portable Document Format'},
                {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
            ];
        }
    });

    // 4. 模拟 languages
    Object.defineProperty(navigator, 'languages', {
        get: function() { return ['zh-CN', 'zh', 'en-US', 'en']; }
    });

    // 5. 清除 Permission 异常
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ||
        parameters.name === 'clipboard-read' ||
        parameters.name === 'clipboard-write'
            ? Promise.resolve({ state: 'prompt', onchange: null })
            : originalQuery(parameters)
    );

    // 6. Canvas 指纹噪声（轻微随机化）
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        if (this.width > 16 && this.height > 16) {
            const ctx = this.getContext('2d');
            if (ctx) {
                ctx.fillStyle = 'rgba(0,0,0,0.01)';
                ctx.fillRect(0, 0, 1, 1);
            }
        }
        return originalToDataURL.apply(this, arguments);
    };

    // 7. WebGL 指纹噪声
    const getParameterProxyHandler = {
        apply: function(target, thisArg, args) {
            const param = args[0];
            if (param === 37445) { return 'Intel Inc.'; }
            if (param === 37446) { return 'Intel Iris OpenGL Engine'; }
            return target.apply(thisArg, args);
        }
    };
    const getParameterProto = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = new Proxy(getParameterProto, getParameterProxyHandler);

    // 8. 覆盖 Notification.permission
    Object.defineProperty(Notification, 'permission', {
        get: function() { return 'default'; }
    });
    """


def _simulate_mouse_movement(driver, start_x, start_y, end_x, end_y):
    """模拟人类鼠标移动：贝塞尔曲线 + 随机抖动 + 变速"""
    sel = _get_selenium()
    if not sel:
        return
    ActionChains = sel["ActionChains"]

    # 控制点：在起点和终点之间随机偏移
    cp_x = (start_x + end_x) / 2 + random.randint(-100, 100)
    cp_y = (start_y + end_y) / 2 + random.randint(-50, 50)

    steps = random.randint(15, 35)
    chain = ActionChains(driver)

    for i in range(1, steps + 1):
        t = i / steps
        # 贝塞尔曲线
        x, y = _bezier_curve((start_x, start_y), (cp_x, cp_y), (end_x, end_y), t)
        # 添加随机抖动（±2px）
        x += random.uniform(-2, 2)
        y += random.uniform(-2, 2)
        chain.move_by_offset(x - start_x, y - start_y)
        start_x, start_y = x, y
        # 每 5 步暂停一次，模拟人类手的停顿
        if i % 5 == 0:
            chain.pause(random.uniform(0.02, 0.08))

    chain.perform()


def _simulate_human_scrolling(driver):
    """模拟人类阅读滚动：变速、回滚、停留"""
    sel = _get_selenium()
    if not sel:
        return
    By = sel["By"]

    # 获取页面总高度
    total_height = driver.execute_script("return document.body.scrollHeight")
    viewport_height = driver.execute_script("return window.innerHeight")
    if total_height <= viewport_height:
        return

    current_y = 0
    scroll_direction = 1  # 1 = down, -1 = up

    while current_y < total_height - viewport_height and scroll_direction == 1:
        # 变速滚动：开始快，接近目标慢（ease-out）
        remaining = total_height - viewport_height - current_y
        step = min(random.randint(200, 600), remaining)

        # 偶尔小步滚动（模拟仔细阅读）
        if random.random() < 0.3:
            step = random.randint(80, 200)

        driver.execute_script(f"window.scrollBy(0, {step});")
        current_y += step

        # 阅读停顿：内容越长停得越久
        pause_time = random.uniform(0.5, 3.0)
        # 如果在图片或视频附近，停更久
        try:
            imgs = driver.find_elements(By.TAG_NAME, "img")
            videos = driver.find_elements(By.TAG_NAME, "video")
            if imgs or videos:
                pause_time += random.uniform(0.5, 1.5)
        except Exception:
            pass
        time.sleep(pause_time)

        # 偶尔回滚（模拟回头查看）
        if random.random() < 0.15 and current_y > 300:
            rollback = random.randint(100, 300)
            driver.execute_script(f"window.scrollBy(0, -{rollback});")
            current_y -= rollback
            time.sleep(random.uniform(0.8, 2.0))

        # 10% 概率提前结束（模拟快速浏览）
        if random.random() < 0.1:
            break

    # 最后缓慢回到顶部附近（不是精确的 0，避免太机械）
    final_y = random.randint(0, 100)
    driver.execute_script(f"window.scrollTo(0, {final_y});")
    time.sleep(random.uniform(0.3, 0.8))


def _simulate_reading_pauses(driver):
    """模拟阅读停顿：在段落、标题附近多停留"""
    sel = _get_selenium()
    if not sel:
        return
    By = sel["By"]

    try:
        # 在文章段落附近多停留
        paragraphs = driver.find_elements(By.TAG_NAME, "p")
        for p in paragraphs[:random.randint(2, 5)]:
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", p)
                time.sleep(random.uniform(1.0, 3.0))
            except Exception:
                pass
    except Exception:
        pass


def _simulate_random_clicks(driver):
    """模拟随机点击：偶尔点击内容区域或空白处"""
    sel = _get_selenium()
    if not sel:
        return
    By = sel["By"]

    try:
        # 70% 概率不点击，保持自然
        if random.random() > 0.3:
            return

        # 优先点击内容链接
        links = driver.find_elements(By.CSS_SELECTOR, "article a, .content a, main a")
        if links and random.random() < 0.5:
            target = random.choice(links[:5])
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
            time.sleep(random.uniform(0.5, 1.2))
            # 只悬停不实际点击（避免跳转）
            sel["ActionChains"](driver).move_to_element(target).pause(random.uniform(0.2, 0.6)).perform()
        else:
            # 点击空白区域
            blank_x = random.randint(100, 800)
            blank_y = random.randint(100, 600)
            driver.execute_script(f"document.elementFromPoint({blank_x}, {blank_y}).click();")
    except Exception:
        pass



# ---------- 记忆系统 ----------
SPIDER_MEMORY_DIR = Path.home() / ".fr_cli" / "spider"
SPIDER_MEMORY_FILE = SPIDER_MEMORY_DIR / "memory.json"
SPIDER_EVOLUTION_FILE = SPIDER_MEMORY_DIR / "evolution.json"


def _ensure_spider_memory_dir():
    SPIDER_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _load_spider_memory():
    """加载爬虫记忆（域名 → 策略映射）"""
    _ensure_spider_memory_dir()
    if not SPIDER_MEMORY_FILE.exists():
        return {}
    try:
        with open(SPIDER_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_spider_memory(memory):
    """保存爬虫记忆"""
    _ensure_spider_memory_dir()
    try:
        with open(SPIDER_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _get_domain_strategy(domain, memory=None):
    """获取指定域名的策略，若无则返回 None"""
    if memory is None:
        memory = _load_spider_memory()
    return memory.get(domain)


def _update_domain_strategy_in_memory(domain, strategy, success=True, memory=None):
    """更新内存中的域名策略（不立即写盘，爬取结束后统一保存）"""
    if memory is None:
        memory = _load_spider_memory()

    existing = memory.get(domain, {})
    existing.update(strategy)

    existing["success_count"] = existing.get("success_count", 0) + (1 if success else 0)
    existing["failure_count"] = existing.get("failure_count", 0) + (0 if success else 1)
    existing["total_attempts"] = existing.get("total_attempts", 0) + 1
    existing["last_used"] = datetime.now().isoformat()
    existing["success_rate"] = existing["success_count"] / max(existing["total_attempts"], 1)

    memory[domain] = existing
    return memory


def _sanitize_filename(url):
    """将 URL 转换为安全的文件名"""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_")
    if not path:
        path = "index"
    name = f"{parsed.netloc}_{path}"
    name = re.sub(r'[^\w\-_]', '_', name)[:100]
    return name + ".html"


# ---------- AI 页面分析 ----------
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


# ---------- 智能链接提取 ----------
def _extract_with_selector(html, selector, base_url):
    """使用 CSS 选择器提取链接（需要 bs4）"""
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


def _extract_links_regex(html, base_url):
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


def _extract_links_smart(html, base_url, state, memory=None):
    """
    智能链接提取：先尝试记忆策略，失败则 AI 分析，再失败回退正则
    返回 (links, extraction_method)
    """
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



# ---------- 自适应请求 ----------
def _fetch_adaptive(url, state, memory=None, force_selenium=False):
    """
    自适应获取页面：根据域名记忆选择最佳获取方式
    返回 (html, err, method_used)
    """
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


def _fetch_with_requests(url):
    """使用 requests Session 获取页面，模拟完整浏览器指纹"""
    requests = _get_requests()
    if not requests:
        return None, "requests 未安装 (pip install requests)"

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


def _fetch_with_selenium(url):
    """使用 selenium / undetected-chromedriver 完全模拟真人浏览"""
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


def _save_page(url, html, output_dir):
    """保存页面到工作区"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(url)
    filepath = output_dir / filename
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)


# ---------- 主爬取逻辑 ----------
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


# ---------- 入口 ----------
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
