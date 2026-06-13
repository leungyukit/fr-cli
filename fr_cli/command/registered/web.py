"""
注册表分组：网络类工具
- search_web / fetch_web
"""
from fr_cli.command.registry import register, _TRIGGERS_WEB
from fr_cli.core.result import Result


@register(
    name="search_web",
    triggers=_TRIGGERS_WEB,
    description="网络搜索",
    params={"query": str},
    security="sec_fetch_web",
    aliases=["/web"],
)
def _search_web(deps, **kwargs):
    result = deps.web_c.search(kwargs["query"], deps.lang)
    if result.is_fail():
        return Result.fail(result.error)
    return Result.ok("\n".join([f"- {r['title']}\n  {r['url']}\n  {r['snippet'][:50]}..." for r in result.unwrap()]))


@register(
    name="fetch_web",
    triggers=_TRIGGERS_WEB,
    description="抓取网页",
    params={"url": str},
    security="sec_fetch_web",
    aliases=["/fetch"],
)
def _fetch_web(deps, **kwargs):
    result = deps.web_c.fetch(kwargs["url"], deps.lang)
    return result
