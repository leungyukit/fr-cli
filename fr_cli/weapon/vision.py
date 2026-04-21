"""
天眼视觉引擎
对接智谱 CogView 画图与 GLM-4V 看图能力
"""
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import CYAN, RESET
import base64, os

def gen_img(client, prompt, out_dir, lang):
    """
    调用 CogView 生成图片并保存到本地
    :return: tuple (是否成功 bool, 本地路径或错误信息 str)
    """
    print(f"{CYAN}{T('gen_ing', lang)}{RESET}")
    try:
        response = client.images.generations(
            model="cogview-3-plus", # 使用最新版画图模型
            prompt=prompt,
            size="1024x1024"
        )
        if response.data and response.data[0].url:
            # 智谱返回的是临时URL，需下载保存到本地
            import requests
            img_url = response.data[0].url
            res = requests.get(img_url, timeout=15)
            res.raise_for_status()

            os.makedirs(out_dir, exist_ok=True)
            safe_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in prompt[:30])
            local_path = os.path.join(out_dir, f"img_{safe_name}.png")
            
            with open(local_path, "wb") as f:
                f.write(res.content)
            return True, local_path
        return False, T("gen_fail", lang) + "No URL"
    except Exception as e: return False, f"{T('gen_fail', lang)} {e}"

def prep_see_msg(messages, img_path, user_text, vfs=None):
    """
    为 GLM-4V 准备带图的上下文 (不直接请求，而是构造好 messages 返回给主循环)
    :param vfs: VFS 实例，若提供则通过沙盒读取本地文件
    """
    msg_content = []
    # 如果是本地文件，转为 base64
    # 优先使用 VFS 沙盒路径解析；若无 VFS 则回退到 os.path（测试兼容）
    is_local = False
    if vfs is not None:
        resolved = vfs._resolve(img_path)
        is_local = resolved is not None and resolved.exists()
    else:
        is_local = os.path.exists(img_path)

    if is_local:
        fh = vfs._resolve(img_path) if vfs is not None else Path(img_path)
        with open(fh, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        msg_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })
    else:
        # 直接当做 URL 处理
        msg_content.append({
            "type": "image_url",
            "image_url": {"url": img_path}
        })
    
    if user_text:
        msg_content.append({"type": "text", "text": user_text})
    else:
        msg_content.append({"type": "text", "text": "请描述这张图片的内容。"})
        
    messages.append({"role": "user", "content": msg_content})
    return messages