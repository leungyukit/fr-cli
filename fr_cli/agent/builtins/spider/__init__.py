"""
@spider 内置 Agent —— 自适应智能网页爬虫助手

模块拆分：
- deps: requests / selenium / undetected_chromedriver / bs4 延迟加载与 Session 管理
- evasion: 浏览器指纹规避 + 人类行为模拟（贝塞尔曲线、滚动、阅读停顿、随机点击）
- memory: 域名策略记忆与本地文件命名
- analyzer: AI 页面分析 + 智能链接提取（CSS 选择器 / 正则回退）
- fetcher: 自适应获取（requests → selenium 自动降级）
- crawler: 主爬取流程、反思进化、REPL 入口
"""
from fr_cli.agent.builtins.spider.crawler import crawl, handle_spider

__all__ = ["crawl", "handle_spider"]
