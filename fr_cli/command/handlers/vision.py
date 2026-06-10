"""命令处理器 —— vision"""

from fr_cli.command.registry import register

@register(
    name="analyze_image",
    triggers=["分析图片", "识图", "看图", "describe image", "图片内容", "识别图片", "生成图片", "画图", "画一张"],
    description="图片分析",
    params={"path": str, "text": str},
    security="sec_read",
    aliases=["/see"],
    needs_msgs=True,
)
def _analyze_image(deps, msgs=None, **kwargs):
    from fr_cli.weapon.vision import prep_see_msg
    from fr_cli.core.stream import stream_cnt
    if not msgs:
        return None, "No message history available"
    prep_see_msg(msgs, kwargs["path"], kwargs.get("text", ""), vfs=deps.vfs)
    txt, _, response_time, _ = stream_cnt(deps.client, deps.model_name, msgs, deps.lang)
    return f"图片分析结果:\n{txt}\n耗时: {response_time:.2f}秒", None


@register(
    name="generate_image",
    description="生成图片",
    params={"prompt": str},
    security="sec_gen_img",
)
def _generate_image(deps, **kwargs):
    from fr_cli.weapon.vision import gen_img
    out_dir = deps.vfs.cwd if deps.vfs else "."
    ok, res = gen_img(deps.client, kwargs["prompt"], out_dir, deps.lang)
    return (res, None) if ok else (None, res)


# ------------------------------------------------------------------

