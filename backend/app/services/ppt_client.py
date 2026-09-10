from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import sys
import time

import requests
from flask import current_app


class PPTv2Client:
    def __init__(self):
        self.app_id = current_app.config.get("XFYUN_APP_ID", "")
        self.api_secret = current_app.config.get("XFYUN_API_SECRET", "")
        self.base_url = current_app.config.get("XFYUN_PPT_API_BASE", "https://zwapi.xfyun.cn/api/aippt")
        print(f"[PPTv2Client] app_id={repr(self.app_id)[:30]} api_secret={'***' if self.api_secret else repr(self.api_secret)}", file=sys.stderr)

    @staticmethod
    def _signature(app_id: str, api_secret: str, timestamp: str) -> str:
        auth = hashlib.md5(f"{app_id}{timestamp}".encode()).hexdigest()
        sign = hmac.new(api_secret.encode(), auth.encode(), hashlib.sha1).digest()
        return base64.b64encode(sign).decode()

    def _headers(self) -> dict:
        ts = str(int(time.time()))
        return {
            "appId": self.app_id,
            "timestamp": ts,
            "signature": self._signature(self.app_id, self.api_secret, ts),
            "Content-Type": "application/json",
        }

    @property
    def enabled(self) -> bool:
        return bool(self.app_id and self.api_secret)

    def get_theme_list(self) -> list[dict]:
        """查询 PPT 模板列表（POST），返回全部可用主题。

        接口文档：https://zwapi.xfyun.cn/api/ppt/v2/template/list
        - Body: {style, color, industry, pageNum, pageSize}
        """
        body = {"style": "", "color": "", "industry": "", "pageNum": 1, "pageSize": 100}
        resp = requests.post(
            "https://zwapi.xfyun.cn/api/ppt/v2/template/list",
            headers=self._headers(), json=body, timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        logging.info("XFYUN themeList response: %s", str(data)[:2000])
        if data.get("code") != 0:
            raise RuntimeError(data.get("message") or data.get("desc") or "获取主题列表失败")
        # 响应格式：{flag, code, desc, data: {total, records: [{templateIndexId, ...}]}}
        inner = data.get("data", {})
        if isinstance(inner, dict):
            return inner.get("records", [])
        return []

    def create_outline(self, query: str, theme: str = "auto", language: str = "cn", search: bool = False) -> dict:
        headers = self._headers()
        headers.pop("Content-Type", None)
        resp = requests.post(
            "https://zwapi.xfyun.cn/api/ppt/v2/createOutline",
            headers=headers,
            data={"query": query, "language": language, "search": str(search).lower()},
            timeout=120,
        )
        if not resp.ok:
            logging.error("XFYUN createOutline v2 HTTP %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("message") or data.get("desc") or "大纲生成失败"
            logging.error("XFYUN createOutline v2 业务错误 code=%s message=%s full=%s",
                          data.get("code"), msg, str(data)[:500])
            raise RuntimeError(msg)
        return data.get("data", {})

    def create_outline_by_doc(
        self,
        file_bytes: bytes,
        file_name: str,
        query: str = "",
        language: str = "cn",
        search: bool = False,
    ) -> dict:
        """基于上传文档生成 PPT 大纲，对应科大讯飞 createOutlineByDoc v2。"""
        headers = self._headers()
        headers.pop("Content-Type", None)
        data = {
            "fileName": file_name,
            "language": language,
            "search": str(search).lower(),
        }
        if query:
            data["query"] = query[:12000]
        resp = requests.post(
            "https://zwapi.xfyun.cn/api/ppt/v2/createOutlineByDoc",
            headers=headers,
            data=data,
            files={"file": (file_name, file_bytes)},
            timeout=120,
        )
        if not resp.ok:
            logging.error("XFYUN createOutlineByDoc v2 HTTP %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            msg = payload.get("message") or payload.get("desc") or "文档大纲生成失败"
            logging.error("XFYUN createOutlineByDoc v2 业务错误 code=%s message=%s full=%s",
                          payload.get("code"), msg, str(payload)[:500])
            raise RuntimeError(msg)
        return payload.get("data", {})

    def create_by_sid(self, sid: str, outline: str, theme: str = "auto", language: str = "cn", author: str = "智文") -> dict:
        logging.info("XFYUN createBySid sid=%s outline_type=%s outline_preview=%s...",
                      sid, type(outline).__name__, str(outline)[:300])
        body = {"sid": sid, "outline": outline, "theme": theme, "language": language, "author": author}
        resp = requests.post(
            f"{self.base_url}/createBySid",
            headers=self._headers(),
            json=body,
            timeout=30,
        )
        if not resp.ok:
            logging.error("XFYUN createBySid HTTP %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("message") or "未知错误"
            logging.error("XFYUN createBySid 业务错误 code=%s message=%s full=%s",
                          data.get("code"), msg, str(data)[:500])
            raise RuntimeError(msg)
        return data.get("data", {})

    def create_ppt_by_outline_v2(
        self,
        query: str,
        outline: dict,
        outline_sid: str = "",
        template_id: str = "",
        author: str = "讯飞智文",
        is_card_note: bool = False,
        is_figure: bool = False,
        ai_image: str = "",
        search: bool = False,
        language: str = "cn",
        page_count: int = 0,
    ) -> dict:
        """通过大纲生成 PPT（v2 接口），对应科大讯飞 createPptByOutline"""
        body = {
            "query": query,
            "outline": outline,
            "author": author,
            "isCardNote": is_card_note,
            "isFigure": is_figure,
            "search": search,
            "language": language,
        }
        if page_count:
            body["pageCount"] = page_count
        if outline_sid:
            body["outlineSid"] = outline_sid
        if template_id and template_id != "auto":
            body["templateId"] = template_id
        if ai_image:
            body["aiImage"] = ai_image
        logging.info("XFYUN createPptByOutline v2 body=%s", str(body)[:500])
        resp = requests.post(
            "https://zwapi.xfyun.cn/api/ppt/v2/createPptByOutline",
            headers=self._headers(),
            json=body,
            timeout=120,
        )
        if not resp.ok:
            logging.error("XFYUN createPptByOutline v2 HTTP %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("message") or data.get("desc") or "未知错误"
            logging.error("XFYUN createPptByOutline v2 业务错误 code=%s message=%s full=%s",
                          data.get("code"), msg, str(data)[:500])
            raise RuntimeError(msg)
        return data.get("data", {})
        logging.info("XFYUN createByOutline body outline=%s...", str(body.get("outline", ""))[:200])
        resp = requests.post(
            f"{self.base_url}/createByOutline",
            headers=self._headers(),
            json=body,
            timeout=120,
        )
        if not resp.ok:
            logging.error("XFYUN createByOutline HTTP %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("message") or "未知错误"
            logging.error("XFYUN createByOutline 业务错误 code=%s message=%s full=%s",
                          data.get("code"), msg, str(data)[:500])
            raise RuntimeError(msg)
        return data.get("data", {})

    def create_by_outline(
        self,
        query: str,
        outline,
        theme: str = "auto",
        language: str = "cn",
        author: str = "讯飞智文",
        create_model: str = "auto",
        is_card_note: bool = False,
        is_cover_img: bool = False,
        is_figure: bool = False,
        page_count: int = 0,
        modules: dict | None = None,
    ) -> dict:
        """兼容旧路由名称，实际调用 PPTv2 createPptByOutline。"""
        template_id = "" if theme in ("", "auto") else theme
        return self.create_ppt_by_outline_v2(
            query=query,
            outline=outline,
            template_id=template_id,
            author=author,
            is_card_note=is_card_note,
            is_figure=is_figure or is_cover_img,
            language=language,
            page_count=page_count,
        )

    def get_progress(self, sid: str) -> dict:
        resp = requests.get(
            "https://zwapi.xfyun.cn/api/ppt/v2/progress",
            headers=self._headers(),
            params={"sid": sid},
            timeout=10,
        )
        if not resp.ok:
            logging.error("XFYUN progress v2 HTTP %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("message") or data.get("desc") or "查询进度失败"
            logging.error("XFYUN progress v2 业务错误 code=%s message=%s full=%s",
                          data.get("code"), msg, str(data)[:500])
            raise RuntimeError(msg)
        result = data.get("data", {}) or {}
        status = result.get("pptStatus")
        if status == "build_failed":
            raise RuntimeError(result.get("errMsg") or "PPT 生成失败")
        if result.get("pptUrl"):
            result["process"] = 100
        else:
            total_pages = int(result.get("totalPages") or 0)
            done_pages = int(result.get("donePages") or 0)
            if total_pages > 0:
                result["process"] = min(99, max(1, round(done_pages / total_pages * 96)))
            elif status == "building":
                result["process"] = 70
            else:
                result["process"] = 0
        return result
