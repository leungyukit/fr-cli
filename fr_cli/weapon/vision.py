"""
天眼视觉引擎
对接智谱 CogView 画图与 GLM-4V 看图能力
"""
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import RED, GREEN, CYAN, DIM, RESET
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
            
            os.makedirs(out_dir, exist_ok=True)
            safe_name = prompt[:20].replace(" ", "_").replace("/", "_")
            local_path = os.path.join(out_dir, f"img_{safe_name}.png")
            
            with open(local_path, "wb") as f:
                f.write(res.content)
            return True, local_path
        return False, T("gen_fail", lang) + "No URL"
    except Exception as e: return False, f"{T('gen_fail', lang)} {e}"

def prep_see_msg(messages, img_path, user_text):
    """
    为 GLM-4V 准备带图的上下文 (不直接请求，而是构造好 messages 返回给主循环)
    """
    msg_content = []
    # 如果是本地文件，转为 base64
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
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