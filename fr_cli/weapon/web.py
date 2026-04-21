"""
互联网游侠
零配置的网页搜索与正文抽取
依赖: requests (pip install requests)
"""
import re
from fr_cli.lang.i18n import T
try:
    import requests
    HAS_REQ = True
except ImportError:
    HAS_REQ = False

class WebRaider:
    def search(self, q, lang):
        """使用百度搜索进行零配置搜索"""
        if not HAS_REQ: return None, "❌ pip install requests"
        try:
            import urllib.parse
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            # 百度搜索
            url = f"https://www.baidu.com/s?wd={urllib.parse.quote(q)}"
            res = requests.get(url, headers=headers, timeout=8)
            
            # 简易正则提取结果
            results = []
            
            # 方法1：匹配任何包含href的a标签和后面的文本
            blocks = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', res.text, re.IGNORECASE)
            for link, title in blocks:
                clean_title = title.strip()
                # 过滤掉太短的标题和明显的非结果链接
                if clean_title and len(clean_title) > 8 and 'baidu.com' not in link:
                    results.append({"title": clean_title, "url": link, "snippet": "点击查看详情"})
                    if len(results) >= 5:
                        break
            
            return results[:5], None
        except Exception as e: return None, f"{T('web_err', lang)} {e}"

    def fetch(self, url, lang):
        """抓取指定 URL 的网页并提取纯文本"""
        if not HAS_REQ: return None, "❌ pip install requests"
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            
            # 极简 HTML 标签剥离
            text = re.sub(r'<script[^>]*>.*?</script>', '', res.text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # 截断过长的文本
            if len(text) > 3000:
                text = text[:3000] + "\n\n...[Truncated]"
            return text, None
        except Exception as e: return None, f"{T('web_err', lang)} {e}"