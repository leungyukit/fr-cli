"""
反爬虫绕过 —— 浏览器指纹规避 + 人类行为模拟

包含：
- 贝塞尔曲线鼠标轨迹
- webdriver 指纹规避脚本
- 人类滚动 / 阅读停顿 / 随机点击
"""
import random
import time


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
    from fr_cli.agent.builtins.spider.deps import _get_selenium
    sel = _get_selenium()
    if not sel:
        return
    ActionChains = sel["ActionChains"]

    # 控制点：在起点和终点之间随机偏移
    cp_x = (start_x + end_x) / 2 + random.randint(-100, 100)
    cp_y = (start_y + end_y) / 2 + random.randint(-100, 100)

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
    from fr_cli.agent.builtins.spider.deps import _get_selenium
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
    from fr_cli.agent.builtins.spider.deps import _get_selenium
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
    from fr_cli.agent.builtins.spider.deps import _get_selenium
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
