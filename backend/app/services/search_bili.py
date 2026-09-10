# -*- coding: utf-8 -*-
"""
B站视频搜索模块（已修复 -101 未登录问题）
使用 WBI 签名 + Cookie 调用官方搜索接口
"""

import hashlib
import os
import re
import time
from urllib.parse import urlencode
import requests

# ====================== B站 Cookie 配置 ======================
# 优先使用环境变量 BILI_COOKIE，未设置时使用下方硬编码值作为兜底
# Bilibili Cookie is read only from the environment. Never commit login credentials.
BILI_COOKIE = os.getenv("BILI_COOKIE", "").strip()

WBI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
WBI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/all/v2"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

def _build_headers(cookie: str = "") -> dict:
    """构建请求头，优先使用传入的 cookie，否则使用默认 cookie"""
    headers = DEFAULT_HEADERS.copy()
    selected_cookie = cookie.strip() or BILI_COOKIE
    if selected_cookie:
        headers["Cookie"] = selected_cookie
    return headers

def _get_wbi_keys(cookie: str = "") -> tuple[str, str]:
    try:
        resp = requests.get(WBI_NAV_URL, headers=_build_headers(cookie), timeout=10)
        data = resp.json()

        # 即使未登录，B站也会返回 wbi_img 和 wbi_sub
        wbi_img = data.get("data", {}).get("wbi_img", {}).get("img_url", "")
        wbi_sub = data.get("data", {}).get("wbi_img", {}).get("sub_url", "")

        if not wbi_img or not wbi_sub:
            raise RuntimeError("未获取到 wbi_img / wbi_sub")

        img_key = re.search(r"/([^/]+)\.png", wbi_img).group(1)
        sub_key = re.search(r"/([^/]+)\.png", wbi_sub).group(1)
        return img_key, sub_key

    except Exception as e:
        raise RuntimeError(f"获取WBI密钥失败：{e}") from e

def _encrypt_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """B站官方 WBI 签名算法（正确版）"""
    # 官方固定混淆串
    MIXIN_KEY = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45,
        41, 9, 17, 36, 27, 24, 0, 1, 61, 54, 55, 56, 57, 60, 51,
        42, 43, 59, 4, 48, 38, 12, 29, 37, 49, 52, 14, 39, 40, 25,
        13, 21, 22, 33, 34, 35, 11, 26, 7, 6, 20, 19, 28, 16, 44,
        5, 30
    ]
    all_key = img_key + sub_key
    mix_key = "".join([all_key[i] for i in MIXIN_KEY])[:32]

    params["wts"] = str(int(time.time()))
    items = sorted(params.items())
    q = urlencode(items)
    w_rid = hashlib.md5((q + mix_key).encode()).hexdigest()

    ret = dict(items)
    ret["w_rid"] = w_rid
    return ret

def search_bili_video(keyword: str, limit: int = 5, cookie: str = ""):
    try:
        img_key, sub_key = _get_wbi_keys(cookie)
        params = {"keyword": keyword, "page": 1, "page_size": limit}
        signed_params = _encrypt_wbi(params, img_key, sub_key)

        resp = requests.get(
            WBI_SEARCH_URL,
            params=signed_params,
            headers=_build_headers(cookie),
            timeout=15
        )
        data = resp.json()

        code = data.get("code")
        if code == -101:
            return {"videos": [], "need_cookie": True, "message": "B站Cookie已过期或未登录，请重新设置Cookie"}
        if code != 0:
            return {"videos": [], "need_cookie": False, "message": f"B站搜索接口返回错误（code={code}）"}

        videos = []
        for item in data.get("data", {}).get("result", []):
            if item.get("result_type") != "video":
                continue
            for v in item.get("data", []):
                videos.append({
                    "title": re.sub(r"<[^>]+>", "", v.get("title", "")),
                    "bvid": v.get("bvid", ""),
                    "link": f"https://www.bilibili.com/video/{v.get('bvid')}",
                    "play": v.get("play", 0),
                    "duration": v.get("duration", ""),
                    "author": v.get("author", ""),
                })
                if len(videos) >= limit:
                    break
            if len(videos) >= limit:
                break
        return {"videos": videos, "need_cookie": False, "message": ""}

    except Exception as e:
        return {"videos": [], "need_cookie": True, "message": f"搜索请求失败，可能是网络或Cookie问题：{str(e)[:80]}"}

def search_bili_video_simple(keyword: str, limit=3, cookie: str = ""):
    result = search_bili_video(keyword, limit, cookie)
    return result.get("videos", [])

if __name__ == "__main__":
    import json
    res = search_bili_video_simple("深度学习", 3)
    print(json.dumps(res, ensure_ascii=False, indent=2))
