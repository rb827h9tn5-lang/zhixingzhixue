from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import os
import re
import requests
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename
import json as _json
import time as _time

from ..extensions import db
from ..models import KnowledgeDocument, PptInnovationAnalysis, PptRecord, Profile
from ..services.profile_evolver import evolve_profile_from_behavior
from ..services.ppt_client import PPTv2Client

ppt_bp = Blueprint("ppt", __name__)

THEMES = [
    {"value": "auto", "label": "智能推荐"},
    {"value": "", "label": "典雅紫"},
    {"value": "", "label": "清新绿"},
    {"value": "", "label": "淡雅蓝"},
    {"value": "", "label": "简约灰"},
    {"value": "", "label": "星空夜影"},
    {"value": "", "label": "炽热暖阳"},
    {"value": "", "label": "幻翠奇旅"},
]

FALLBACK_THEMES = THEMES  # 当官方 API 不可用时使用
# 静态兜底主题 value 均为空字符串，仅保留"auto"用于判断
STATIC_THEME_VALUES = {"auto"}

LANGUAGES = [
    {"value": "cn", "label": "中文简体"},
    {"value": "en", "label": "英语"},
    {"value": "ja", "label": "日语"},
    {"value": "ru", "label": "俄语"},
    {"value": "ko", "label": "韩语"},
    {"value": "de", "label": "德语"},
    {"value": "fr", "label": "法语"},
    {"value": "pt", "label": "葡萄牙语"},
    {"value": "es", "label": "西班牙语"},
    {"value": "it", "label": "意大利语"},
    {"value": "th", "label": "泰语"},
]

CREATE_MODELS = [
    {"value": "auto", "label": "智能判断"},
    {"value": "topic", "label": "话题生成（150 字内）"},
    {"value": "text", "label": "长文本生成"},
]


@ppt_bp.get("/themes")
@jwt_required()
def themes():
    """从科大讯飞官方 API 获取主题列表，失败时使用静态兜底数据"""
    client = PPTv2Client()
    if client.enabled:
        try:
            api_themes = client.get_theme_list()
            if api_themes:
                # API 返回格式：[{templateIndexId, color, style, industry, detailImage(JSON string)}, ...]
                import json as _json
                mapped = []
                for t in api_themes:
                    # 构造模板名称：风格 + 颜色
                    style = t.get("style", "")
                    color = t.get("color", "")
                    label = f"{style} {color}".strip() or "未命名模板"
                    # 从 detailImage 中提取缩略图：可能是 JSON 字符串，也可能是直接 URL
                    thumbnail = ""
                    detail = t.get("detailImage", "")
                    if detail:
                        if isinstance(detail, str) and detail.strip().startswith("{"):
                            try:
                                imgs = _json.loads(detail)
                                thumbnail = imgs.get("titleCoverImageLarge") or imgs.get("titleCoverImage") or ""
                            except Exception:
                                pass
                        else:
                            thumbnail = detail.strip()
                    mapped.append({
                        "value": t["templateIndexId"],
                        "label": label,
                        "thumbnail": thumbnail,
                    })
                # 前置插入"智能推荐"选项
                return jsonify({"themes": [{"value": "auto", "label": "智能推荐", "thumbnail": ""}, *mapped]})
        except Exception as exc:
            current_app.logger.warning("获取讯飞 PPT 主题列表失败: %s", exc)
            pass  # 降级到静态数据
    return jsonify({"themes": FALLBACK_THEMES})


def normalize_template_id(template_id) -> str:
    """v2 接口需要真实模板 ID；空值、auto 和静态兜底主题都使用默认模板。"""
    value = (template_id or "").strip()
    if not value or value == "auto":
        return ""
    return value


def create_ppt_by_outline_with_template_retry(client: PPTv2Client, **kwargs):
    template_id = normalize_template_id(kwargs.pop("template_id", ""))
    try:
        return client.create_ppt_by_outline_v2(template_id=template_id, **kwargs)
    except RuntimeError as exc:
        message = str(exc)
        if template_id and ("模板" in message or "100009" in message or "未知错误" in message):
            current_app.logger.warning("PPT 模板 %s 不可用，自动去掉模板后重试：%s", template_id, message)
            return client.create_ppt_by_outline_v2(template_id="", **kwargs)
        raise


def truncate_xfyun_query(query: str) -> str:
    """讯飞 PPTv2 createOutline/createPptByOutline 的 query 上限为 12000 字。"""
    return (query or "").strip()[:12000]


def clean_outline_title(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^[-*•]\s*", "", text)
    text = re.sub(r"^(?:第?[一二三四五六七八九十\d]+[章节部分]?|[一二三四五六七八九十\d]+)[\.、\)\s]+", "", text)
    return text.strip("：: \t")


def text_outline_to_xfyun_json(outline_text: str, fallback_title: str = "PPT 生成") -> dict:
    """将用户手动输入的文本大纲解析成讯飞 createPptByOutline 所需 JSON。

    这里是兜底解析，不再为了格式转换调用通用 LLM，避免 PPT 链路误走 DashScope。
    """
    lines = [line.rstrip() for line in (outline_text or "").splitlines() if line.strip()]
    title = clean_outline_title(fallback_title) or "PPT 生成"
    chapters: list[dict] = []
    current: dict | None = None

    if lines and not re.match(r"^\s*(?:[-*•]|\d+[\.)、]|第?[一二三四五六七八九十\d]+[章节部分]?[\.、\)\s])", lines[0]):
        first = clean_outline_title(lines[0])
        if first and len(first) <= 80:
            title = first
            lines = lines[1:]

    for raw in lines:
        stripped = raw.strip()
        cleaned = clean_outline_title(stripped)
        if not cleaned:
            continue

        is_indented = raw[:1].isspace()
        is_bullet = bool(re.match(r"^[-*•]\s+", stripped))
        is_numbered = bool(re.match(r"^(?:\d+[\.)、]|第?[一二三四五六七八九十\d]+[章节部分]?[\.、\)\s])", stripped))
        if not is_indented and (is_numbered or not current):
            current = {"chapterTitle": cleaned[:120], "chapterContents": []}
            chapters.append(current)
            continue

        if is_indented or is_bullet:
            if current is None:
                current = {"chapterTitle": cleaned[:120], "chapterContents": []}
                chapters.append(current)
            else:
                current.setdefault("chapterContents", []).append({"chapterTitle": cleaned[:120]})
            continue

        current = {"chapterTitle": cleaned[:120], "chapterContents": []}
        chapters.append(current)

    if not chapters:
        chapters = [{"chapterTitle": title, "chapterContents": []}]

    return {
        "title": title[:120],
        "subTitle": "AI 自动生成演示文稿",
        "chapters": chapters[:20],
    }


def coerce_xfyun_outline(outline, fallback_title: str = "PPT 生成") -> dict:
    if isinstance(outline, dict):
        if isinstance(outline.get("chapters"), list):
            return outline
        if isinstance(outline.get("outline"), dict):
            return coerce_xfyun_outline(outline["outline"], fallback_title)
    if isinstance(outline, str):
        text = outline.strip()
        if text:
            try:
                parsed = _json.loads(text)
                return coerce_xfyun_outline(parsed, fallback_title)
            except Exception:
                return text_outline_to_xfyun_json(text, fallback_title)
    return text_outline_to_xfyun_json("", fallback_title)


def current_user_id() -> int:
    return int(get_jwt_identity())


def ensure_ppt_record(sid: str, title: str, template_id: str = ""):
    if not sid:
        return None
    user_id = current_user_id()
    record = PptRecord.query.filter_by(user_id=user_id, sid=sid).first()
    if record:
        if title and record.title == "未命名 PPT":
            record.title = title[:180]
        return record
    record = PptRecord(
        user_id=user_id,
        sid=sid,
        title=(title or "未命名 PPT")[:180],
        template_id=template_id or "",
        status="generating",
    )
    db.session.add(record)
    db.session.commit()
    return record


def upsert_ppt_analysis_basis(record: PptRecord | None, basis: dict | None) -> None:
    if not record or not basis:
        return
    analysis = PptInnovationAnalysis.query.filter_by(user_id=record.user_id, ppt_record_id=record.id).first()
    if not analysis:
        analysis = PptInnovationAnalysis(
            user_id=record.user_id,
            ppt_record_id=record.id,
            sid=record.sid or "",
            status="pending",
        )
        db.session.add(analysis)
    merged = dict(analysis.basis or {})
    merged.update({key: value for key, value in basis.items() if value not in (None, "")})
    analysis.sid = record.sid or analysis.sid
    analysis.basis = merged
    if analysis.status != "ready":
        analysis.status = "pending"
    db.session.commit()


def extract_ppt_url(result: dict) -> str:
    for key in ("pptUrl", "ppt_url", "fileUrl", "file_url", "url", "downloadUrl", "download_url"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = result.get("data")
    if isinstance(data, dict):
        return extract_ppt_url(data)
    return ""


def save_ppt_file(url: str, sid: str) -> tuple[str, str]:
    if not url:
        return "", ""
    if "/api/uploads/" in url:
        return url, ""
    backend_dir = Path(__file__).resolve().parents[2]
    target_dir = backend_dir / "uploads" / "generated_ppts"
    target_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1] or ".pptx"
    if ext.lower() not in {".ppt", ".pptx"}:
        ext = ".pptx"
    filename = f"{sid or int(_time.time())}{ext}"
    local_path = target_dir / filename
    resp = requests.get(url, timeout=180, stream=True)
    resp.raise_for_status()
    with open(local_path, "wb") as file:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)
    if not local_path.exists() or local_path.stat().st_size <= 0:
        raise RuntimeError("PPT 文件保存失败")
    return f"/api/uploads/generated_ppts/{filename}", str(local_path)


def update_ppt_record_from_progress(sid: str, result: dict):
    record = PptRecord.query.filter_by(user_id=current_user_id(), sid=sid).first()
    if not record:
        return None
    ppt_url = extract_ppt_url(result)
    process = int(float(result.get("process") or result.get("progress") or 0))
    if ppt_url:
        record.remote_url = ppt_url
        if not record.local_url:
            try:
                record.local_url, record.local_path = save_ppt_file(ppt_url, sid)
            except Exception as exc:
                current_app.logger.warning("PPT 本地保存失败 sid=%s: %s", sid, exc)
                record.local_url = ppt_url
        record.status = "completed"
    elif process >= 100:
        record.status = "completed"
    else:
        record.status = "generating"
    db.session.commit()
    return record


def remove_local_ppt_file(record: PptRecord) -> None:
    local_path = record.local_path or ""
    if not local_path:
        return
    backend_dir = Path(__file__).resolve().parents[2]
    upload_dir = (backend_dir / "uploads").resolve()
    target = Path(local_path).resolve()
    if upload_dir not in target.parents:
        current_app.logger.warning("拒绝删除 uploads 外部文件：%s", target)
        return
    if target.exists() and target.is_file():
        target.unlink()


@ppt_bp.get("/languages")
@jwt_required()
def languages():
    return jsonify({"languages": LANGUAGES})


@ppt_bp.get("/create-models")
@jwt_required()
def create_models():
    return jsonify({"create_models": CREATE_MODELS})


@ppt_bp.post("/quick-create")
@jwt_required()
def quick_create():
    """一键快速生成 PPT：XFYUN createOutline → XFYUN createPptByOutline → 返回 sid"""
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"message": "请输入 PPT 主题"}), 400
    if len(topic) > 2000:
        return jsonify({"message": "主题过长，最多 2000 字"}), 400

    template_id = data.get("template_id", "auto")
    language = data.get("language", "cn")
    author = (data.get("author") or "").strip() or "讯飞智文"
    is_card_note = bool(data.get("is_card_note", False))
    is_figure = bool(data.get("is_figure", False))
    search = bool(data.get("search", False))
    ai_image = (data.get("ai_image") or "").strip()
    page_count = int(data.get("page_count") or 0)

    # Step 1: 调用科大讯飞 PPTv2 createOutline 生成结构化大纲
    try:
        page_hint = f"目标页数约 {page_count} 页，请控制章节数量与内容密度。" if page_count else ""
        outline_query = truncate_xfyun_query(f"{topic}\n{page_hint}".strip())
        outline_result = client.create_outline(outline_query, language=language, search=search)
        outline_sid = outline_result.get("sid", "")
        json_outline = coerce_xfyun_outline(outline_result.get("outline"), topic)
        current_app.logger.info("quick-create XFYUN outline: %s", _json.dumps(json_outline, ensure_ascii=False)[:500])
    except RuntimeError as exc:
        return jsonify({"message": f"大纲生成失败：{exc}"}), 502
    except Exception as exc:
        return jsonify({"message": f"大纲生成服务异常：{exc}"}), 502

    # Step 2: 调用 XFYUN createPptByOutline v2 生成 PPT
    try:
        result = create_ppt_by_outline_with_template_retry(
            client,
            query=truncate_xfyun_query(topic),
            outline=json_outline,
            outline_sid=outline_sid,
            template_id=template_id,
            author=author,
            is_card_note=is_card_note,
            is_figure=is_figure,
            ai_image=ai_image,
            search=search,
            language=language,
            page_count=page_count,
        )
        record = ensure_ppt_record(result.get("sid", ""), topic, template_id)
        upsert_ppt_analysis_basis(record, {
            "mode": "quick",
            "topic": topic,
            "outline_sid": outline_sid,
            "json_outline": json_outline,
            "template_id": template_id,
            "language": language,
            "author": author,
            "is_card_note": is_card_note,
            "is_figure": is_figure,
            "search": search,
            "ai_image": ai_image,
            "page_count": page_count,
        })
        # 更新用户动态画像
        user_id = int(get_jwt_identity())
        profile = Profile.query.filter_by(user_id=user_id).first()
        if profile:
            now = _time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{now}] 生成 PPT：{topic[:80]}{'…' if len(topic) > 80 else ''}"
            profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()
            profile.engagement_pattern = "PPT 制作 + 资源整合"
            evolve_profile_from_behavior(profile, "generate_ppt", {
                "topic": topic,
                "template_id": template_id,
                "page_count": page_count,
            })
            db.session.commit()
        return jsonify({"sid": result.get("sid", "")})
    except RuntimeError as exc:
        current_app.logger.error("quick-create createPptByOutline v2 RuntimeError: %s", exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        current_app.logger.error("quick-create createPptByOutline v2 异常: %s", exc)
        return jsonify({"message": f"PPT 生成服务异常：{exc}"}), 502


@ppt_bp.post("/outline-from-doc")
@jwt_required()
def outline_from_doc():
    """上传文档生成大纲：调用科大讯飞 PPTv2 createOutlineByDoc。"""
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    if "file" not in request.files:
        return jsonify({"message": "请上传文件"}), 400

    file = request.files["file"]
    if file.filename == "" or not file.filename:
        return jsonify({"message": "文件不能为空"}), 400

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext.lower() not in {"pdf", "doc", "docx", "txt", "md"}:
        return jsonify({"message": "仅支持 pdf、doc、docx、txt、md 文件"}), 400

    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"message": "文件内容不能为空"}), 400
    if len(file_bytes) > 10 * 1024 * 1024:
        return jsonify({"message": "文件过大，最大支持 10MB"}), 400

    query = truncate_xfyun_query(request.form.get("query") or "请根据上传文档生成一份结构清晰、适合课堂汇报的 PPT 大纲")
    language = request.form.get("language") or "cn"
    search = str(request.form.get("search") or "").lower() in {"1", "true", "yes", "on"}
    try:
        result = client.create_outline_by_doc(file_bytes, filename, query=query, language=language, search=search)
        return jsonify({"sid": result.get("sid", ""), "outline": result.get("outline", "")})
    except RuntimeError as exc:
        return jsonify({"message": f"大纲生成失败：{exc}"}), 502
    except Exception as exc:
        return jsonify({"message": f"大纲生成服务异常：{exc}"}), 502


@ppt_bp.post("/generate-content")
@jwt_required()
def generate_ppt_content():
    """基于科大讯飞 PPTv2 大纲接口生成 Markdown 预览内容。"""
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"message": "请输入 PPT 主题或要求"}), 400
    if len(query) > 12000:
        return jsonify({"message": "内容过长，最多 12000 字"}), 400

    try:
        outline_result = client.create_outline(truncate_xfyun_query(query), language=data.get("language", "cn"), search=bool(data.get("search", False)))
        outline = coerce_xfyun_outline(outline_result.get("outline"), query)
        lines = [f"# {outline.get('title') or query}"]
        subtitle = outline.get("subTitle")
        if subtitle:
            lines.extend(["", f"> {subtitle}"])
        for chapter in outline.get("chapters", []):
            title = chapter.get("chapterTitle") if isinstance(chapter, dict) else str(chapter)
            if not title:
                continue
            lines.extend(["", f"## {title}"])
            contents = chapter.get("chapterContents") if isinstance(chapter, dict) else []
            if isinstance(contents, list):
                for item in contents:
                    item_title = item.get("chapterTitle") if isinstance(item, dict) else str(item)
                    if item_title:
                        lines.append(f"- {item_title}")
        return jsonify({"sid": outline_result.get("sid", ""), "outline": outline, "content": "\n".join(lines)})
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        return jsonify({"message": f"内容生成服务异常：{exc}"}), 502


@ppt_bp.post("/create-by-outline")
@jwt_required()
def create_by_outline():
    """通过 query + outline 直接生成 PPT，对应科大讯飞 createByOutline 接口"""
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    outline_payload = data.get("outline")
    outline_text = outline_payload if isinstance(outline_payload, str) else ""
    outline = coerce_xfyun_outline(outline_payload, query or "PPT 生成")
    if not query or not outline:
        return jsonify({"message": "参数不完整，需要 query 和 outline"}), 400

    theme = data.get("theme", "auto")
    language = data.get("language", "cn")
    author = data.get("author", "智文")
    create_model = data.get("create_model", "auto")
    is_card_note = bool(data.get("is_card_note", False))
    is_cover_img = bool(data.get("is_cover_img", False))
    is_figure = bool(data.get("is_figure", False))
    page_count = int(data.get("page_count", 0))
    modules = data.get("modules", {})

    try:
        result = client.create_by_outline(
            query=truncate_xfyun_query(query),
            outline=outline,
            theme=theme,
            language=language,
            author=author,
            create_model=create_model,
            is_card_note=is_card_note,
            is_cover_img=is_cover_img,
            is_figure=is_figure,
            page_count=page_count,
            modules=modules,
        )
        record = ensure_ppt_record(result.get("sid", ""), query, theme)
        upsert_ppt_analysis_basis(record, {
            "mode": "outline",
            "topic": query,
            "outline": outline_text,
            "json_outline": outline,
            "template_id": theme,
            "language": language,
            "author": author,
            "page_count": page_count,
        })
        return jsonify({"sid": result.get("sid", "")})
    except RuntimeError as exc:
        current_app.logger.error("createByOutline RuntimeError: %s", exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        current_app.logger.error("createByOutline 异常: %s", exc)
        return jsonify({"message": f"PPT 生成服务异常：{exc}"}), 502


@ppt_bp.post("/create-by-sid")
@jwt_required()
def create_by_sid():
    """基于已有大纲 SID 生成 PPT，对应科大讯飞 createBySid 接口"""
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    data = request.get_json(silent=True) or {}
    sid = (data.get("sid") or "").strip()
    if not sid:
        return jsonify({"message": "参数不完整，需要 sid"}), 400

    raw_outline = data.get("raw_outline")
    outline_text = (data.get("outline") or "").strip()
    format_mode = data.get("format", "")

    # format=llm 是旧前端参数名。这里改成本地解析，PPT 链路不再调用 DashScope/Qwen。
    if format_mode == "llm" and outline_text:
        try:
            outline = coerce_xfyun_outline(outline_text, data.get("query") or "PPT 生成")
        except RuntimeError as exc:
            return jsonify({"message": f"大纲格式转换失败：{exc}"}), 502
        except Exception as exc:
            return jsonify({"message": f"大纲转换服务异常：{exc}"}), 502
    else:
        outline = coerce_xfyun_outline(raw_outline if isinstance(raw_outline, dict) else outline_text, data.get("query") or "PPT 生成")
        if not outline:
            return jsonify({"message": "参数不完整，需要 outline"}), 400

    theme = data.get("theme", "auto")
    language = data.get("language", "cn")
    author = (data.get("author") or "").strip() or "讯飞智文"
    is_card_note = bool(data.get("is_card_note", False))
    is_figure = bool(data.get("is_figure", False))
    search = bool(data.get("search", False))
    ai_image = (data.get("ai_image") or "").strip()
    page_count = int(data.get("page_count") or 0)

    try:
        # v2 接口接受 JSON 对象 outline，直接传给 createPptByOutline
        result = create_ppt_by_outline_with_template_retry(
            client,
            query=truncate_xfyun_query(data.get("query", "") or data.get("outline", "") or "PPT 生成"),
            outline=outline,
            outline_sid=sid,
            template_id=theme,
            author=author,
            is_card_note=is_card_note,
            is_figure=is_figure,
            ai_image=ai_image,
            search=search,
            language=language,
            page_count=page_count,
        )
        if isinstance(outline_text, str) and outline_text.splitlines():
            fallback_title = outline_text.splitlines()[0]
        else:
            fallback_title = "PPT 生成"
        record = ensure_ppt_record(result.get("sid", ""), data.get("query") or fallback_title, theme)
        upsert_ppt_analysis_basis(record, {
            "mode": "outline",
            "topic": data.get("query") or fallback_title,
            "outline": outline_text or data.get("outline") or "",
            "json_outline": outline if isinstance(outline, dict) else None,
            "raw_outline": raw_outline if isinstance(raw_outline, dict) else None,
            "template_id": theme,
            "language": language,
            "author": author,
            "is_card_note": is_card_note,
            "is_figure": is_figure,
            "search": search,
            "ai_image": ai_image,
            "page_count": page_count,
        })
        # 更新用户动态画像
        user_id = int(get_jwt_identity())
        profile = Profile.query.filter_by(user_id=user_id).first()
        if profile:
            now = _time.strftime("%Y-%m-%d %H:%M:%S")
            query_text = (data.get("query") or data.get("outline") or "")[:80]
            line = f"[{now}] 基于大纲生成 PPT：{query_text[:80]}{'…' if len(query_text) > 80 else ''}"
            profile.raw_dialogue = ((profile.raw_dialogue or "") + "\n" + line).strip()
            profile.engagement_pattern = "PPT 制作 + 资源整合"
            evolve_profile_from_behavior(profile, "generate_ppt", {
                "topic": data.get("query") or fallback_title,
                "outline": data.get("outline") or outline_text,
                "template_id": theme,
            })
            db.session.commit()
        return jsonify({"sid": result.get("sid", "")})
    except RuntimeError as exc:
        current_app.logger.error("createPptByOutline v2 RuntimeError: %s", exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        current_app.logger.error("createPptByOutline v2 异常: %s", exc)
        return jsonify({"message": f"PPT 生成服务异常：{exc}"}), 502


@ppt_bp.post("/outline")
@jwt_required()
def create_outline():
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"message": "请输入 PPT 主题或要求"}), 400
    if len(query) > 12000:
        return jsonify({"message": "内容过长，最多 12000 字"}), 400

    theme = data.get("theme", "auto")
    language = data.get("language", "cn")
    search = bool(data.get("search", False))
    try:
        result = client.create_outline(truncate_xfyun_query(query), normalize_template_id(theme), language=language, search=search)
        return jsonify({"sid": result.get("sid", ""), "outline": result.get("outline", "")})
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        return jsonify({"message": f"大纲生成服务异常：{exc}"}), 502


@ppt_bp.post("/generate")
@jwt_required()
def generate():
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    data = request.get_json(silent=True) or {}
    sid = (data.get("sid") or "").strip()
    outline = (data.get("outline") or "").strip()
    if not sid or not outline:
        return jsonify({"message": "参数不完整"}), 400

    theme = data.get("theme", "auto")
    language = data.get("language", "cn")
    try:
        result = client.create_by_sid(sid, outline, theme, language)
        return jsonify({"sid": result.get("sid", ""), "process": result.get("process", 0)})
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        return jsonify({"message": f"PPT 生成服务异常：{exc}"}), 502


@ppt_bp.get("/progress/<sid>")
@jwt_required()
def progress(sid: str):
    client = PPTv2Client()
    if not client.enabled:
        return jsonify({"message": "请配置 XFYUN_APP_ID 和 XFYUN_API_SECRET"}), 400

    try:
        result = client.get_progress(sid)
        record = update_ppt_record_from_progress(sid, result)
        ppt_url = (record.local_url if record and record.local_url else "") or extract_ppt_url(result)
        process = int(float(result.get("process") or result.get("progress") or 0))
        if ppt_url:
            process = 100
            upsert_ppt_analysis_basis(record, {
                "ppt_url": ppt_url,
                "progress": process,
                "progress_raw": result,
            })
        return jsonify({
            "process": process,
            "pptUrl": ppt_url,
            "record": record.to_dict() if record else None,
            "raw": result,
        })
    except RuntimeError as exc:
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        return jsonify({"message": f"查询进度异常：{exc}"}), 502


@ppt_bp.get("/history")
@jwt_required()
def ppt_history():
    records = (
        PptRecord.query
        .filter_by(user_id=current_user_id())
        .order_by(PptRecord.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"records": [record.to_dict() for record in records]})


@ppt_bp.post("/history")
@jwt_required()
def save_history():
    data = request.get_json(silent=True) or {}
    sid = (data.get("sid") or "").strip()
    title = (data.get("title") or data.get("query") or "未命名 PPT").strip()
    ppt_url = (data.get("ppt_url") or data.get("pptUrl") or "").strip()
    template_id = (data.get("template_id") or data.get("theme") or "").strip()

    if not sid and not ppt_url:
        return jsonify({"message": "缺少 sid 或 PPT 下载链接"}), 400

    record = ensure_ppt_record(sid or f"local-{int(_time.time())}", title, template_id)
    if ppt_url and record:
        record.remote_url = ppt_url
        if not record.local_url or "/api/uploads/" not in record.local_url:
            try:
                record.local_url, record.local_path = save_ppt_file(ppt_url, record.sid)
            except Exception as exc:
                current_app.logger.warning("PPT 历史保存本地文件失败 sid=%s: %s", record.sid, exc)
                record.local_url = ppt_url
        record.status = "completed"
        db.session.commit()
        upsert_ppt_analysis_basis(record, {
            "topic": title,
            "template_id": template_id,
            "ppt_url": ppt_url,
            "status": record.status,
        })

    return jsonify({"record": record.to_dict() if record else None})


@ppt_bp.get("/history/<int:record_id>/innovation-analysis")
@jwt_required()
def ppt_innovation_analysis(record_id: int):
    user_id = current_user_id()
    record = PptRecord.query.filter_by(id=record_id, user_id=user_id).first()
    if not record:
        return jsonify({"message": "记录不存在"}), 404
    return jsonify({
        "evaluation": None,
        "basis": None,
        "status": "unavailable",
        "cached": False,
        "message": "真实证据验证工作流尚未启用",
    })


@ppt_bp.delete("/history/<int:record_id>")
@jwt_required()
def delete_history(record_id: int):
    record = PptRecord.query.filter_by(id=record_id, user_id=current_user_id()).first()
    if not record:
        return jsonify({"message": "记录不存在"}), 404
    try:
        remove_local_ppt_file(record)
    except Exception as exc:
        current_app.logger.warning("删除本地 PPT 文件失败 record=%s: %s", record_id, exc)
    PptInnovationAnalysis.query.filter_by(user_id=current_user_id(), ppt_record_id=record.id).delete()
    db.session.delete(record)
    db.session.commit()
    return jsonify({"message": "PPT 历史记录已删除"})
