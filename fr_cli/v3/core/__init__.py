"""fr_cli.v3.core 基础设施

注意: container / lifecycle / provider / pipeline / errors 等未接线设施
已在死代码清理中移除(生产代码零引用)。保留 events + plugin。
"""
from fr_cli.v3.core.events import *
from fr_cli.v3.core.plugin import *
