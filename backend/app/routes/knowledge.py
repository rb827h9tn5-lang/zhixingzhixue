from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Course, KnowledgeDocument, KnowledgeRelation
from ..services.knowledge_ingestion import (
    persist_ingestion,
    prepare_ingestion,
    upsert_course,
)
from ..services.local_generator import LocalStudyGenerator
from ..services.rag_store import format_source_citation, hybrid_query_chunks, split_text
from ..services.text_cleaner import (
    clean_extracted_text,
    filter_chunks,
    filter_document_pages,
    is_bad_text,
)
from ..services.vector_store import clear_user_index, rebuild_user_index

knowledge_bp = Blueprint("knowledge", __name__)
SUPPORTED_FILE_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".pdf", ".docx"}
BUILTIN_COURSE_CODE = "AI-INTRO"
BUILTIN_COURSE_FILENAME = "artificial_intelligence.pdf"


def current_user_id() -> int:
    return int(get_jwt_identity())


def is_builtin_document(document: KnowledgeDocument) -> bool:
    return bool((document.metadata_json or {}).get("is_builtin"))


def document_payload(document: KnowledgeDocument) -> dict:
    structured_chunk_count = len(document.structured_chunks)
    return {
        "id": document.id,
        "course_id": document.course_id,
        "chapter_id": document.chapter_id,
        "title": document.title,
        "doc_type": document.doc_type or "文本",
        "source_filename": document.source_filename or document.title,
        "source_type": document.source_type,
        "processing_status": document.processing_status,
        "page_count": document.page_count,
        "content_hash": document.content_hash,
        "metadata": document.metadata_json or {},
        "chunk_count": structured_chunk_count or len(document.chunks or []),
        "is_builtin": is_builtin_document(document),
        "created_at": document.created_at.isoformat(),
    }


def decode_text_file(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def extract_pdf_text(raw: bytes) -> str:
    """使用 PyMuPDF（fitz）提取 PDF 文本，逐页清洗过滤。

    优先使用 PyMuPDF（解析质量更好），
    如果未安装则回退到 pypdf。
    对扫描页或乱码严重的页，尝试 OCR 兜底。
    """
    pages = extract_pdf_pages(raw)

    if not pages:
        return ""

    # 逐页过滤：清洗 + 坏文本检测 + 目录页检测
    valid_pages = filter_document_pages(pages)

    if not valid_pages:
        return ""

    # 组装有效页
    parts = []
    for page in valid_pages:
        parts.append(f"## 第 {page['page']} 页\n{page['text']}")
    return "\n\n".join(parts)


def extract_pdf_pages(raw: bytes) -> list[dict]:
    pages = _try_extract_with_pymupdf(raw)
    if pages is None:
        pages = _try_extract_with_pypdf(raw)
    return pages or []


def _try_extract_with_pymupdf(raw: bytes) -> list[dict] | None:
    """尝试使用 PyMuPDF（fitz）提取文本，返回 [{page, text}]。"""
    try:
        import fitz
    except ImportError:
        return None

    try:
        doc = fitz.open(stream=raw, filetype="pdf")
        pages = []
        for page_index, page in enumerate(doc):
            text = page.get_text("text") or ""
            # 如果提取的文本过少或乱码严重，尝试 OCR
            if _should_ocr(text):
                ocr_text = _ocr_page(page)
                if ocr_text:
                    text = ocr_text
            pages.append({"page": page_index + 1, "text": text})
        doc.close()
        return pages
    except Exception:
        return None


def _try_extract_with_pypdf(raw: bytes) -> list[dict] | None:
    """回退方案：使用 pypdf 提取文本。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(BytesIO(raw))
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": page_number, "text": text})
        return pages
    except Exception:
        return None


def _should_ocr(text: str, min_chars: int = 50, bad_ratio_threshold: float = 0.3) -> bool:
    """判断是否需要对该页使用 OCR。

    条件：
    - 文本过短（< 50 字符）
    - 有效文本比例过低（可能为扫描图）
    """
    text = text.strip()
    if not text or len(text) < min_chars:
        return True
    valid = sum(1 for c in text if c.isprintable())
    if valid / max(len(text), 1) < bad_ratio_threshold:
        return True
    return False


def _ocr_page(page) -> str:
    """OCR 兜底：将 PDF 页面渲染为图片后识别文字。

    优先使用 paddleocr（如果已安装），否则返回空字符串。
    """
    try:
        from PIL import Image
        # 将 PDF 页面渲染为高分辨率图片
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    except Exception:
        return ""

    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False, use_gpu=False)
        result = ocr.ocr(img, cls=True)
        if not result or not result[0]:
            return ""
        lines = []
        for line_info in result[0]:
            text = line_info[1][0] if len(line_info) > 1 else ""
            if text.strip():
                lines.append(text.strip())
        return "\n".join(lines)
    except ImportError:
        return ""
    except Exception:
        return ""


def extract_docx_text(raw: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("DOCX 解析依赖未安装，请执行 pip install python-docx") from exc

    document = Document(BytesIO(raw))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_uploaded_file(file_storage) -> tuple[str, str, list[dict], str]:
    filename = Path(file_storage.filename or "课程材料.txt").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_FILE_EXTENSIONS:
        supported = "、".join(sorted(SUPPORTED_FILE_EXTENSIONS))
        raise ValueError(f"暂不支持 {suffix or '无后缀'} 文件，请上传：{supported}")

    raw = file_storage.read()
    if suffix in {".txt", ".md", ".markdown", ".csv", ".json"}:
        content = decode_text_file(raw)
        pages = [{"page": 1, "text": content}]
    elif suffix == ".pdf":
        pages = extract_pdf_pages(raw)
        valid_pages = filter_document_pages(pages)
        content = "\n\n".join(
            f"## 第 {page['page']} 页\n{page['text']}"
            for page in valid_pages
        )
    elif suffix == ".docx":
        content = extract_docx_text(raw)
        pages = [{"page": 1, "text": content}]
    else:
        content = ""
        pages = []
    return filename, content, pages, hashlib.sha256(raw).hexdigest()


def rebuild_index_with_report(user_id: int, document: KnowledgeDocument, report: dict) -> bool:
    indexed = False
    try:
        docs = KnowledgeDocument.query.filter_by(user_id=user_id).all()
        indexed = rebuild_user_index(user_id, [doc.to_dict() for doc in docs])
    except Exception:
        indexed = False

    current_report = dict(report)
    current_report["vector_indexed"] = indexed
    metadata = dict(document.metadata_json or {})
    metadata["import_report"] = current_report
    document.metadata_json = metadata
    document.processing_status = "indexed" if indexed else "parsed"
    db.session.commit()
    return indexed


def ingest_pages(
    *,
    user_id: int,
    title: str,
    filename: str,
    doc_type: str,
    source_type: str,
    content_hash: str,
    pages: list[dict],
    course: Course | None = None,
    is_builtin: bool = False,
):
    plan = prepare_ingestion(pages)
    if not plan.chunks:
        raise ValueError("文档经清洗后无有效内容，请检查文件是否可正常读取")

    document, report, idempotent = persist_ingestion(
        user_id=user_id,
        title=Path(title).name,
        source_filename=filename,
        doc_type=doc_type,
        source_type=source_type,
        content_hash=content_hash,
        plan=plan,
        course=course,
    )
    if is_builtin and not idempotent:
        metadata = dict(document.metadata_json or {})
        metadata["is_builtin"] = True
        document.metadata_json = metadata
        db.session.commit()
    if not idempotent:
        rebuild_index_with_report(user_id, document, report)
        report = dict((document.metadata_json or {}).get("import_report") or report)
    return document, report, idempotent


@knowledge_bp.post("/upload")
@jwt_required()
def upload_document():
    user_id = current_user_id()
    if "file" in request.files:
        file = request.files["file"]
        try:
            filename, content, pages, content_hash = extract_uploaded_file(file)
        except (RuntimeError, ValueError) as exc:
            return jsonify({"message": str(exc)}), 400
        title = request.form.get("title") or filename
        raw_course_id = request.form.get("course_id")
        suffix = Path(filename).suffix.lower()
        type_map = {".txt": "TXT", ".md": "Markdown", ".markdown": "Markdown", ".csv": "CSV", ".json": "JSON", ".pdf": "PDF", ".docx": "DOCX"}
        doc_type = type_map.get(suffix, "文件")
    else:
        data = request.get_json(silent=True) or {}
        title = data.get("title") or "课程材料"
        content = data.get("content") or ""
        pages = [{"page": 1, "text": content}]
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        raw_course_id = data.get("course_id")
        filename = f"{Path(title).name}.txt"
        doc_type = "文本"

    if not content.strip():
        return jsonify({"message": "文档内容为空，无法写入知识库"}), 400

    try:
        course = db.session.get(Course, int(raw_course_id)) if raw_course_id else None
    except (TypeError, ValueError):
        return jsonify({"message": "course_id 格式不正确"}), 400
    if raw_course_id and not course:
        return jsonify({"message": "课程不存在"}), 404

    try:
        document, report, idempotent = ingest_pages(
            user_id=user_id,
            title=title,
            filename=filename,
            doc_type=doc_type,
            source_type="upload",
            content_hash=content_hash,
            pages=pages,
            course=course,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception("知识库文档入库失败")
        return jsonify({"message": "文档入库失败，请稍后重试"}), 500
    return jsonify({
        "document": document_payload(document),
        "import_report": report,
        "idempotent": idempotent,
    })


@knowledge_bp.get("/courses")
@jwt_required()
def list_courses():
    courses = Course.query.order_by(Course.created_at.desc()).all()
    return jsonify({"courses": [course.to_dict() for course in courses]})


@knowledge_bp.get("/courses/<int:course_id>")
@jwt_required()
def course_detail(course_id: int):
    course = Course.query.filter_by(id=course_id).first_or_404()
    relations = KnowledgeRelation.query.filter_by(course_id=course.id).all()
    documents = KnowledgeDocument.query.filter_by(
        user_id=current_user_id(),
        course_id=course.id,
    ).order_by(KnowledgeDocument.created_at.desc()).all()
    return jsonify({
        "course": course.to_dict(include_chapters=True),
        "relations": [relation.to_dict() for relation in relations],
        "documents": [document_payload(document) for document in documents],
    })


@knowledge_bp.post("/courses/import-builtin")
@jwt_required()
def import_builtin_course():
    pdf_path = Path(current_app.root_path).parent / "knowledge_base" / BUILTIN_COURSE_FILENAME
    if not pdf_path.exists():
        return jsonify({"message": f"内置课程文件不存在：{BUILTIN_COURSE_FILENAME}"}), 404

    raw = pdf_path.read_bytes()
    pages = extract_pdf_pages(raw)
    if not pages:
        return jsonify({"message": "内置课程 PDF 无法解析"}), 400

    plan = prepare_ingestion(pages)
    plan_report = plan.report()
    coverage = {
        "source_filename": BUILTIN_COURSE_FILENAME,
        "expected_chapters": plan_report["expected_chapters"],
        "imported_chapters": plan_report["imported_chapters"],
        "missing_chapters": plan_report["missing_chapters"],
        "chapter_coverage": plan_report["chapter_coverage"],
        "note": "当前仓库 PDF 仅包含目录和第 1 章正文，课程保持 draft 状态。",
    }
    course = upsert_course(
        code=BUILTIN_COURSE_CODE,
        title="人工智能导论",
        description="基于仓库内教材建立的课程知识结构。",
        source_coverage=coverage,
    )
    db.session.commit()

    try:
        document, report, idempotent = ingest_pages(
            user_id=current_user_id(),
            title="人工智能导论",
            filename=BUILTIN_COURSE_FILENAME,
            doc_type="PDF",
            source_type="builtin",
            content_hash=hashlib.sha256(raw).hexdigest(),
            pages=pages,
            course=course,
            is_builtin=True,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception("内置课程导入失败")
        return jsonify({"message": "内置课程导入失败，请查看服务日志"}), 500

    return jsonify({
        "course": course.to_dict(include_chapters=True),
        "document": document_payload(document),
        "import_report": report,
        "idempotent": idempotent,
    })


@knowledge_bp.post("/reindex/<int:document_id>")
@jwt_required()
def reindex_document(document_id: int):
    """对指定文档重新解析、清洗、分块、建索引。

    用于修复已入库的乱码文档：重新提取 → 清洗 → 过滤 → embedding → 建索引。
    """
    user_id = current_user_id()
    document = KnowledgeDocument.query.filter_by(id=document_id, user_id=user_id).first_or_404()

    if document.structured_chunks:
        report = dict((document.metadata_json or {}).get("import_report") or {})
        indexed = rebuild_index_with_report(user_id, document, report)
        message = "文档向量索引重建完成" if indexed else "向量索引重建失败，仍可使用关键词检索"
        return jsonify({"message": message, "document": document_payload(document)})

    # 重新提取和清洗
    raw_content = document.content
    cleaned = clean_extracted_text(raw_content)

    if not cleaned.strip():
        return jsonify({"message": "该文档清洗后无有效内容，无法重新索引"}), 400

    # 重新分块 + 逐块过滤
    raw_chunks = split_text(cleaned)
    valid_chunks = filter_chunks(raw_chunks)

    if not valid_chunks:
        return jsonify({"message": "该文档经重新清洗后无有效 chunks，请删除后重新上传"}), 400

    # 更新文档的 content 和 chunks
    document.content = cleaned
    document.chunks = valid_chunks
    db.session.commit()

    # 重建 FAISS 索引
    try:
        docs = KnowledgeDocument.query.filter_by(user_id=user_id).all()
        ok = rebuild_user_index(user_id, [doc.to_dict() for doc in docs])
        if not ok:
            return jsonify({"message": "文档已重新分块，但 FAISS 索引重建失败（将回退到关键词检索）", "document": document_payload(document)}), 200
    except Exception:
        return jsonify({"message": "文档已重新分块，但索引重建异常", "document": document_payload(document)}), 200

    return jsonify({"message": "文档重新索引完成", "document": document_payload(document)})


@knowledge_bp.get("/documents")
@jwt_required()
def documents():
    docs = KnowledgeDocument.query.filter_by(user_id=current_user_id()).order_by(KnowledgeDocument.created_at.desc()).all()
    return jsonify({"documents": [document_payload(doc) for doc in docs]})


@knowledge_bp.patch("/documents/<int:document_id>")
@jwt_required()
def rename_document(document_id: int):
    document = KnowledgeDocument.query.filter_by(id=document_id, user_id=current_user_id()).first_or_404()
    if is_builtin_document(document):
        return jsonify({"message": "内置知识库文档不允许修改名称"}), 403

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"message": "文档名称不能为空"}), 400
    document.title = title[:180]
    db.session.commit()
    return jsonify({"document": document_payload(document)})


@knowledge_bp.delete("/documents/<int:document_id>")
@jwt_required()
def delete_document(document_id: int):
    user_id = current_user_id()
    document = KnowledgeDocument.query.filter_by(id=document_id, user_id=user_id).first_or_404()
    if is_builtin_document(document):
        return jsonify({"message": "内置知识库文档不允许删除"}), 403

    db.session.delete(document)
    db.session.commit()

    remaining = KnowledgeDocument.query.filter_by(user_id=user_id).all()
    if remaining:
        rebuild_user_index(user_id, [doc.to_dict() for doc in remaining])
    else:
        clear_user_index(user_id)
    return jsonify({"message": "文档已删除"})


@knowledge_bp.post("/query")
@jwt_required()
def query():
    data = request.get_json(silent=True) or {}
    question = data.get("question") or ""
    user_id = current_user_id()
    docs = KnowledgeDocument.query.filter_by(user_id=user_id).all()
    doc_payloads = [doc.to_dict() for doc in docs]
    chunks = hybrid_query_chunks(question, doc_payloads, user_id)
    answer = LocalStudyGenerator().tutor(question)
    if chunks:
        snippets = "\n\n".join(
            f"来源：{format_source_citation(item)}\n> {item['content']}"
            for item in chunks
        )
        answer = f"## 基于知识库的回答\n\n{LocalStudyGenerator().tutor(question)}\n\n## 检索依据\n\n{snippets}"
    return jsonify({"answer": answer, "sources": chunks})
