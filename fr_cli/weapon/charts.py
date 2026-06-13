"""
控制台图表生成器 —— 供大模型与用户调用
纯文本/Unicode 实现，无第三方图形库依赖
支持：柱状图(bar)、饼图(pie)、趋势折线图(line)
"""
import math
from fr_cli.ui.ui import CYAN, GREEN, YELLOW, RED, MAGENTA, RESET
from fr_cli.core.result import Result


_BAR_CHARS = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
_LINE_COLORS = [CYAN, GREEN, YELLOW, RED, MAGENTA]


def _color(text, color, enabled=True):
    return f"{color}{text}{RESET}" if enabled else text


def _to_numbers(values):
    """把字符串或数字列表统一转为浮点数，返回 Result[list]"""
    result = []
    for v in values:
        if isinstance(v, (int, float)):
            result.append(float(v))
        else:
            try:
                result.append(float(v))
            except ValueError:
                return Result.fail(f"无效数值: {v}")
    return Result.ok(result)


def bar_chart(labels, values, title=None, width=40, color=True):
    """生成横向柱状图，返回 Result。"""
    if len(labels) != len(values):
        return Result.fail("labels 和 values 长度不一致")
    if not values:
        return Result.fail("数据不能为空")

    nums_result = _to_numbers(values)
    if nums_result.is_fail():
        return Result.fail(nums_result.error)
    nums = nums_result.unwrap()

    max_val = max(nums)
    if max_val == 0:
        max_val = 1

    max_label_len = max(len(str(l)) for l in labels)
    lines = []
    if title:
        lines.append(_color(f"📊 {title}", CYAN, color))
        lines.append("")

    for label, val in zip(labels, nums):
        ratio = val / max_val
        full = int(ratio * width)
        frac = int((ratio * width - full) * 8)
        if frac >= 8:
            full += 1
            frac = 0
        bar = "█" * full + (_BAR_CHARS[frac] if frac > 0 else "")
        label_str = str(label).ljust(max_label_len)
        lines.append(f"{label_str} │{_color(bar, GREEN, color)} {val}")

    return Result.ok("\n".join(lines))


def pie_chart(labels, values, title=None, width=30, color=True):
    """生成文本饼图，返回 Result。"""
    if len(labels) != len(values):
        return Result.fail("labels 和 values 长度不一致")
    if not values:
        return Result.fail("数据不能为空")

    nums_result = _to_numbers(values)
    if nums_result.is_fail():
        return Result.fail(nums_result.error)
    nums = nums_result.unwrap()

    total = sum(nums)
    if total == 0:
        return Result.fail("数值总和不能为 0")

    percentages = [v / total * 100 for v in nums]

    # 饼图主体：用一行方块近似比例
    bar_width = min(width, 60)
    segments = []
    chars = ["█", "▓", "▒", "░", "▆", "▇", "▄", "▀"]
    for i, pct in enumerate(percentages):
        seg_len = round(pct / 100 * bar_width)
        seg_len = max(1, seg_len) if pct > 0 else 0
        char = chars[i % len(chars)]
        segments.append(_color(char * seg_len, _LINE_COLORS[i % len(_LINE_COLORS)], color))

    lines = []
    if title:
        lines.append(_color(f"🥧 {title}", CYAN, color))
        lines.append("")

    lines.append("".join(segments))
    lines.append("")

    # 图例
    for i, (label, pct) in enumerate(zip(labels, percentages)):
        marker = _color(chars[i % len(chars)], _LINE_COLORS[i % len(_LINE_COLORS)], color)
        lines.append(f"{marker} {label}: {pct:.1f}% ({nums[i]})")

    return Result.ok("\n".join(lines))


def line_chart(labels, values, title=None, width=60, height=15, color=True):
    """生成趋势折线图，返回 Result。"""
    if len(labels) != len(values):
        return Result.fail("labels 和 values 长度不一致")
    if len(values) < 2:
        return Result.fail("折线图至少需要两个数据点")

    nums_result = _to_numbers(values)
    if nums_result.is_fail():
        return Result.fail(nums_result.error)
    nums = nums_result.unwrap()

    min_val = min(nums)
    max_val = max(nums)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1

    # 构建字符网格
    grid = [[" " for _ in range(width)] for _ in range(height)]

    n = len(nums)
    for i in range(n):
        x = int(i / (n - 1) * (width - 1))
        y = height - 1 - int((nums[i] - min_val) / val_range * (height - 1))
        y = max(0, min(height - 1, y))
        grid[y][x] = "●"

    # 连接相邻点（Bresenham 简化版）
    for i in range(n - 1):
        x0 = int(i / (n - 1) * (width - 1))
        x1 = int((i + 1) / (n - 1) * (width - 1))
        y0 = height - 1 - int((nums[i] - min_val) / val_range * (height - 1))
        y1 = height - 1 - int((nums[i + 1] - min_val) / val_range * (height - 1))
        y0 = max(0, min(height - 1, y0))
        y1 = max(0, min(height - 1, y1))
        _draw_line(grid, x0, y0, x1, y1)

    # 构造输出
    lines = []
    if title:
        lines.append(_color(f"📈 {title}", CYAN, color))
        lines.append("")

    # Y 轴刻度
    label_width = max(len(str(math.ceil(max_val))), len(str(math.floor(min_val))))
    for row in range(height):
        val = max_val - row / (height - 1) * val_range
        y_label = f"{val:>{label_width}.0f} │"
        line = y_label + "".join(grid[row])
        lines.append(_color(line, GREEN, color) if row % 2 == 0 else line)

    # X 轴
    lines.append(" " * label_width + " └" + "─" * width)

    # X 轴标签（均匀分布）
    x_labels = [str(l) for l in labels]
    if len(x_labels) <= width // 4:
        positions = [int(i / (len(x_labels) - 1) * (width - 1)) if len(x_labels) > 1 else 0 for i in range(len(x_labels))]
        x_axis = [" "] * width
        for pos, lab in zip(positions, x_labels):
            for j, ch in enumerate(lab):
                if pos + j < width:
                    x_axis[pos + j] = ch
        lines.append(" " * (label_width + 2) + "".join(x_axis))
    else:
        lines.append(" " * (label_width + 2) + x_labels[0].ljust(width // 2) + x_labels[-1].rjust(width - width // 2))

    return Result.ok("\n".join(lines))


def _draw_line(grid, x0, y0, x1, y1):
    """在网格上画一条简单折线"""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    height = len(grid)
    width = len(grid[0]) if height else 0

    x, y = x0, y0
    while True:
        if 0 <= x < width and 0 <= y < height:
            if grid[y][x] == " ":
                if dx > dy:
                    grid[y][x] = "─"
                else:
                    grid[y][x] = "│"
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def generate_chart(chart_type, labels, values, title=None, width=None, height=None, color=True):
    """统一入口，根据类型生成对应图表，返回 Result。"""
    chart_type = str(chart_type).lower()
    if chart_type == "bar":
        return bar_chart(labels, values, title=title, width=width or 40, color=color)
    if chart_type == "pie":
        return pie_chart(labels, values, title=title, width=width or 30, color=color)
    if chart_type == "line":
        return line_chart(labels, values, title=title, width=width or 60, height=height or 15, color=color)
    return Result.fail(f"不支持的图表类型: {chart_type}（支持 bar/pie/line）")
