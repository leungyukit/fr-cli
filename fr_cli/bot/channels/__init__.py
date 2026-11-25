"""
Bot 通道包 —— 平台适配器集合

v2.8.7 新增。

统一适配层的「下半段」：每个平台一个模块，实现
``fr_cli.bot.core.channel.Channel`` 的三个方法（verify / parse / send），
平台差异（验签算法、payload 结构、发送 API）全部收敛在这里，
上层（路由 / 会话 / 去重 / 确认）只面向统一消息编程。

内置通道：
    generic   —— 通用 webhook，任何能往 fr-cli 推 JSON 的场景都能接
    lark      —— 飞书（事件订阅 v2 + 应用消息 API）
    telegram  —— Telegram（Bot API webhook + sendMessage）

用法::

    from fr_cli.bot.channels import load_channels
    load_channels()                       # 触发各模块的 @register_channel

    from fr_cli.bot.core.channel import get_channel
    channel = get_channel("lark", {"secret": "xxx"})
"""
from __future__ import annotations

from typing import List

__all__ = ["load_channels"]


def load_channels() -> List[str]:
    """加载全部内置通道，返回已登记的通道名列表。

    通道类通过 ``@register_channel`` 登记到全局注册表，而装饰器只在
    **模块被 import 时**执行 —— 所以任何想用通道的入口都必须先调用本函数。
    重复调用是幂等的（Python 模块缓存）。
    """
    from . import generic, lark, telegram  # noqa: F401  —— import 即注册

    from fr_cli.bot.core.channel import list_channel_classes

    return list_channel_classes()
