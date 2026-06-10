"""命令处理器 —— web"""

from fr_cli.command.registry import register

@register(
    name="search_web",
    triggers=_TRIGGERS_WEB,
    description="网络搜索",
    params={"query": str},
    security="sec_fetch_web",
    aliases=["/web"],
)
def _search_web(deps, **kwargs):
    res, err = deps.web_c.search(kwargs["query"], deps.lang)
    if err:
        return None, err
    return "\n".join([f"- {r['title']}\n  {r['url']}\n  {r['snippet'][:50]}..." for r in res]), None


@register(
    name="fetch_web",
    triggers=_TRIGGERS_WEB,
    description="抓取网页",
    params={"url": str},
    security="sec_fetch_web",
    aliases=["/fetch"],
)
def _fetch_web(deps, **kwargs):
    txt, err = deps.web_c.fetch(kwargs["url"], deps.lang)
    return (txt, None) if not err else (None, err)


# ------------------------------------------------------------------

