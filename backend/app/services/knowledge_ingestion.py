from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from ..extensions import db
from ..models import (
    Chapter,
    Course,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    KnowledgeRelation,
)
from .rag_store import split_text
from .text_cleaner import clean_extracted_text, is_bad_text, is_toc_like_text


CHAPTER_PATTERN = re.compile(
    r"第\s*([0-9一二三四五六七八九十百]+)\s*章\s*([^\n\r]{1,80})"
)
SECTION_PATTERN = re.compile(
    r"^\s*((?:\d+\.)+\d+)\s*[、.．]?\s*(.{1,100})\s*$"
)
PRINTED_PAGE_PATTERN = re.compile(r"^\s*(\d{3})\s*$")
CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass
class PreparedPage:
    page: int
    text: str
    chapter_order: int | None = None
    chapter_title: str = ""
    printed_page: int | None = None


@dataclass
class PreparedChunk:
    index: int
    text: str
    page: int
    printed_page: int | None
    chapter_order: int | None
    chapter_title: str
    section_code: str = ""
    section_title: str = ""


@dataclass
class IngestionPlan:
    total_pages: int
    valid_pages: list[PreparedPage] = field(default_factory=list)
    skipped_pages: list[dict[str, Any]] = field(default_factory=list)
    failed_pages: list[dict[str, Any]] = field(default_factory=list)
    expected_chapters: dict[int, str] = field(default_factory=dict)
    imported_chapters: dict[int, str] = field(default_factory=dict)
    chunks: list[PreparedChunk] = field(default_factory=list)

    def report(self) -> dict:
        expected_orders = sorted(self.expected_chapters)
        imported_orders = sorted(self.imported_chapters)
        denominator = len(expected_orders) or len(imported_orders)
        coverage = round(len(imported_orders) / denominator, 4) if denominator else 0
        mapped_chunks = sum(1 for chunk in self.chunks if chunk.section_code)
        return {
            "total_pages": self.total_pages,
            "successful_pages": [page.page for page in self.valid_pages],
            "successful_page_count": len(self.valid_pages),
            "skipped_pages": self.skipped_pages,
            "failed_pages": self.failed_pages,
            "expected_chapters": [
                {"order": order, "title": self.expected_chapters[order]}
                for order in expected_orders
            ],
            "imported_chapters": [
                {"order": order, "title": self.imported_chapters[order]}
                for order in imported_orders
            ],
            "missing_chapters": [
                {"order": order, "title": self.expected_chapters[order]}
                for order in expected_orders
                if order not in self.imported_chapters
            ],
            "chapter_coverage": coverage,
            "chunk_count": len(self.chunks),
            "mapped_chunk_count": mapped_chunks,
            "unmapped_chunk_count": len(self.chunks) - mapped_chunks,
        }


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def chinese_number_to_int(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        tens = CHINESE_DIGITS.get(left, 1) if left else 1
        ones = CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(value) == 1:
        return CHINESE_DIGITS.get(value)
    return None


def normalize_heading(value: str) -> str:
    cleaned = clean_extracted_text(value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t。.;；")
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)


def extract_chapters(text: str) -> dict[int, str]:
    chapters: dict[int, str] = {}
    for match in CHAPTER_PATTERN.finditer(text or ""):
        order = chinese_number_to_int(match.group(1))
        title = normalize_heading(match.group(2))
        title = re.split(r"\s{2,}|\d{2,3}\s*$", title)[0].strip()
        if order and title:
            chapters.setdefault(order, title)
    return chapters


def extract_body_chapters(text: str) -> dict[int, str]:
    chapters: dict[int, str] = {}
    for line in (text or "").splitlines():
        line = normalize_heading(line)
        if len(line) > 50 or "介绍" in line or "本章" in line:
            continue
        match = CHAPTER_PATTERN.fullmatch(line)
        if not match:
            continue
        order = chinese_number_to_int(match.group(1))
        title = normalize_heading(match.group(2))
        if order and title:
            chapters.setdefault(order, title)
    return chapters


def extract_printed_page(text: str) -> int | None:
    for line in (text or "").splitlines()[:5]:
        match = PRINTED_PAGE_PATTERN.match(line)
        if match:
            return int(match.group(1))
    return None


def prepare_ingestion(raw_pages: list[dict[str, Any]]) -> IngestionPlan:
    plan = IngestionPlan(total_pages=len(raw_pages))
    cleaned_candidates: list[PreparedPage] = []

    for raw_page in raw_pages:
        page_number = int(raw_page.get("page") or 0)
        raw_text = raw_page.get("text") or ""
        if not raw_text.strip():
            plan.skipped_pages.append({"page": page_number, "reason": "empty"})
            continue

        toc_chapters = extract_chapters(raw_text) if is_toc_like_text(raw_text) else {}
        if toc_chapters:
            plan.expected_chapters.update(toc_chapters)
            plan.skipped_pages.append({"page": page_number, "reason": "table_of_contents"})
            continue

        cleaned = clean_extracted_text(raw_text)
        if is_bad_text(cleaned):
            plan.skipped_pages.append({"page": page_number, "reason": "invalid_text"})
            continue
        cleaned_candidates.append(
            PreparedPage(
                page=page_number,
                text=cleaned,
                printed_page=extract_printed_page(cleaned),
            )
        )

    body_chapter_starts: dict[int, tuple[int, str]] = {}
    for page in cleaned_candidates:
        for order, title in extract_body_chapters(page.text).items():
            body_chapter_starts.setdefault(order, (page.page, title))

    body_start = _find_body_start(cleaned_candidates, body_chapter_starts)
    active_order: int | None = None
    active_title = ""
    for page in cleaned_candidates:
        if body_start and page.page < body_start:
            plan.skipped_pages.append({"page": page.page, "reason": "front_matter"})
            continue
        page_chapters = extract_body_chapters(page.text)
        if page_chapters:
            active_order = sorted(page_chapters)[0]
            active_title = page_chapters[active_order]
            plan.imported_chapters.setdefault(active_order, active_title)
        elif active_order is None and body_chapter_starts:
            active_order = sorted(body_chapter_starts)[0]
            active_title = body_chapter_starts[active_order][1]
            plan.imported_chapters.setdefault(active_order, active_title)
        page.chapter_order = active_order
        page.chapter_title = active_title
        plan.valid_pages.append(page)

    if not plan.expected_chapters:
        plan.expected_chapters.update(plan.imported_chapters)

    plan.chunks = _build_chunks(plan.valid_pages)
    return plan


def _find_body_start(
    pages: list[PreparedPage],
    chapter_starts: dict[int, tuple[int, str]],
) -> int | None:
    if not chapter_starts:
        return None
    first_chapter_page = min(item[0] for item in chapter_starts.values())
    nearby_printed_one = [
        page.page
        for page in pages
        if page.page <= first_chapter_page and page.printed_page == 1
    ]
    if nearby_printed_one:
        return max(nearby_printed_one)
    return first_chapter_page


def _section_heading(line: str) -> tuple[str, str] | None:
    match = SECTION_PATTERN.match(line)
    if not match:
        return None
    code = match.group(1).rstrip(".")
    title = normalize_heading(match.group(2))
    if not title or len(code.split(".")) < 2:
        return None
    return code, title


def _build_chunks(pages: list[PreparedPage]) -> list[PreparedChunk]:
    chunks: list[PreparedChunk] = []
    current_section_code = ""
    current_section_title = ""

    for page in pages:
        blocks: list[tuple[str, str, str]] = []
        buffer: list[str] = []

        def flush():
            if buffer:
                blocks.append(
                    (
                        current_section_code,
                        current_section_title,
                        "\n".join(buffer).strip(),
                    )
                )
                buffer.clear()

        for line in page.text.splitlines():
            heading = _section_heading(line)
            if heading:
                flush()
                current_section_code, current_section_title = heading
            buffer.append(line)
        flush()

        for section_code, section_title, block_text in blocks:
            for text_chunk in split_text(block_text, size=700, overlap=80):
                if is_bad_text(text_chunk):
                    continue
                chunks.append(
                    PreparedChunk(
                        index=len(chunks),
                        text=text_chunk,
                        page=page.page,
                        printed_page=page.printed_page,
                        chapter_order=page.chapter_order,
                        chapter_title=page.chapter_title,
                        section_code=section_code,
                        section_title=section_title,
                    )
                )
    return chunks


def upsert_course(
    *,
    code: str,
    title: str,
    description: str = "",
    source_coverage: dict | None = None,
) -> Course:
    course = Course.query.filter_by(code=code).first()
    if not course:
        course = Course(code=code, title=title)
        db.session.add(course)
    course.title = title
    course.description = description
    course.status = "draft"
    if source_coverage is not None:
        course.source_coverage = source_coverage
    db.session.flush()
    return course


def persist_ingestion(
    *,
    user_id: int,
    title: str,
    source_filename: str,
    doc_type: str,
    source_type: str,
    content_hash: str,
    plan: IngestionPlan,
    course: Course | None = None,
) -> tuple[KnowledgeDocument, dict, bool]:
    duplicate = KnowledgeDocument.query.filter_by(
        user_id=user_id,
        content_hash=content_hash,
    ).first()
    if duplicate:
        report = dict((duplicate.metadata_json or {}).get("import_report") or {})
        report["idempotent"] = True
        return duplicate, report, True

    chapter_map: dict[int, Chapter] = {}
    if course:
        for order, chapter_title in plan.imported_chapters.items():
            chapter = Chapter.query.filter_by(
                course_id=course.id,
                chapter_order=order,
            ).first()
            pages = [page.page for page in plan.valid_pages if page.chapter_order == order]
            if not chapter:
                chapter = Chapter(
                    course_id=course.id,
                    chapter_order=order,
                    title=chapter_title,
                )
                db.session.add(chapter)
            chapter.title = chapter_title
            chapter.start_page = min(pages) if pages else None
            chapter.end_page = max(pages) if pages else None
            chapter.summary = f"正文来源：{source_filename}"
            db.session.flush()
            chapter_map[order] = chapter

    report = plan.report()
    report["idempotent"] = False
    report["vector_indexed"] = False
    content = "\n\n".join(
        f"## 第 {page.page} 页\n{page.text}"
        for page in plan.valid_pages
    )
    only_chapter = next(iter(chapter_map.values())) if len(chapter_map) == 1 else None
    document = KnowledgeDocument(
        user_id=user_id,
        course_id=course.id if course else None,
        chapter_id=only_chapter.id if only_chapter else None,
        title=title,
        doc_type=doc_type,
        source_filename=source_filename,
        source_type=source_type,
        processing_status="parsed",
        page_count=plan.total_pages,
        content_hash=content_hash,
        metadata_json={"import_report": report},
        content=content,
        chunks=[chunk.text for chunk in plan.chunks],
    )
    db.session.add(document)
    db.session.flush()

    knowledge_points = _upsert_knowledge_points(course, chapter_map, plan.chunks)
    chunk_models: list[KnowledgeChunk] = []
    for chunk in plan.chunks:
        chapter = chapter_map.get(chunk.chapter_order or -1)
        point = knowledge_points.get(chunk.section_code)
        chunk_model = KnowledgeChunk(
            document_id=document.id,
            course_id=course.id if course else None,
            chapter_id=chapter.id if chapter else None,
            knowledge_point_id=point.id if point else None,
            chunk_index=chunk.index,
            page_start=chunk.page,
            page_end=chunk.page,
            section=(
                f"{chunk.section_code} {chunk.section_title}".strip()
                if chunk.section_code
                else ""
            ),
            chunk_text=chunk.text,
            content_hash=sha256_text(chunk.text),
            metadata_json={
                "physical_page": chunk.page,
                "printed_page": chunk.printed_page,
                "source_filename": source_filename,
            },
        )
        db.session.add(chunk_model)
        chunk_models.append(chunk_model)
    db.session.flush()

    for chunk_model in chunk_models:
        chunk_model.vector_ref = f"knowledge_chunk:{chunk_model.id}"
    _upsert_hierarchy_relations(course, knowledge_points, chunk_models)
    db.session.commit()
    return document, report, False


def _upsert_knowledge_points(
    course: Course | None,
    chapter_map: dict[int, Chapter],
    chunks: list[PreparedChunk],
) -> dict[str, KnowledgePoint]:
    if not course:
        return {}
    points: dict[str, KnowledgePoint] = {}
    headings: dict[str, tuple[str, int | None]] = {}
    for chunk in chunks:
        if chunk.section_code and chunk.section_title:
            headings.setdefault(
                chunk.section_code,
                (chunk.section_title, chunk.chapter_order),
            )
    for code, (name, chapter_order) in headings.items():
        chapter = chapter_map.get(chapter_order or -1)
        if not chapter:
            continue
        point = KnowledgePoint.query.filter_by(
            course_id=course.id,
            code=code,
        ).first()
        if not point:
            point = KnowledgePoint(
                course_id=course.id,
                chapter_id=chapter.id,
                code=code,
                name=name,
            )
            db.session.add(point)
        point.chapter_id = chapter.id
        point.name = name
        point.description = f"由教材小节标题 {code} 确定性识别"
        point.aliases_json = []
        point.learning_objectives_json = []
        db.session.flush()
        points[code] = point
    return points


def _upsert_hierarchy_relations(
    course: Course | None,
    points: dict[str, KnowledgePoint],
    chunks: list[KnowledgeChunk],
) -> None:
    if not course:
        return
    evidence_by_point = {
        chunk.knowledge_point_id: chunk.id
        for chunk in chunks
        if chunk.knowledge_point_id
    }
    for code, point in points.items():
        if code.count(".") < 2:
            continue
        parent = points.get(code.rsplit(".", 1)[0])
        if not parent:
            continue
        relation = KnowledgeRelation.query.filter_by(
            source_knowledge_point_id=point.id,
            target_knowledge_point_id=parent.id,
            relation_type="belongs_to",
        ).first()
        if not relation:
            relation = KnowledgeRelation(
                course_id=course.id,
                source_knowledge_point_id=point.id,
                target_knowledge_point_id=parent.id,
                relation_type="belongs_to",
                strength=1.0,
            )
            db.session.add(relation)
        relation.evidence_chunk_id = evidence_by_point.get(point.id)
