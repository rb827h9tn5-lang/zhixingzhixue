from __future__ import annotations

import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError


def split_text(text: str, size: int = 600, overlap: int = 80) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    chunks = []
    start = 0
    while start < len(cleaned):
        chunks.append(cleaned[start : start + size])
        start += max(1, size - overlap)
    return chunks


def build_query_keywords(question: str) -> Counter:
    keywords = Counter()
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]{2,}", question or ""):
        keywords[token] += 3
        if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
            max_size = min(6, len(token))
            for size in range(2, max_size + 1):
                for index in range(0, len(token) - size + 1):
                    keywords[token[index:index + size]] += 1
    return keywords


def query_chunks(question: str, documents: list[dict], limit: int = 4) -> list[dict]:
    keywords = build_query_keywords(question)
    scored = []
    for document in documents:
        structured_chunks = document.get("structured_chunks") or []
        chunks = structured_chunks or document.get("chunks", [])
        for chunk_index, chunk in enumerate(chunks):
            content = (
                (chunk.get("chunk_text") or chunk.get("content") or "").strip()
                if isinstance(chunk, dict)
                else chunk.strip() if isinstance(chunk, str) else ""
            )
            if not content:
                continue
            score = sum(content.count(keyword) * weight for keyword, weight in keywords.items())
            if score:
                scored.append(_source_payload(document, chunk, chunk_index, content, score))
    scored.sort(key=lambda item: item["score"], reverse=True)
    if scored:
        return scored[:limit]
    fallback = []
    for document in documents:
        structured_chunks = document.get("structured_chunks") or []
        chunks = structured_chunks or document.get("chunks", [])
        for chunk_index, chunk in enumerate(chunks[:1]):
            content = (
                (chunk.get("chunk_text") or chunk.get("content") or "").strip()
                if isinstance(chunk, dict)
                else chunk.strip() if isinstance(chunk, str) else ""
            )
            if content:
                fallback.append(_source_payload(document, chunk, chunk_index, content, 0))
    return fallback[:limit]


def _source_payload(
    document: dict,
    chunk: dict | str,
    chunk_index: int,
    content: str,
    score: float,
) -> dict:
    payload = {
        "title": document.get("title", "未命名"),
        "source_filename": document.get("source_filename") or document.get("title", "未命名"),
        "document_id": document.get("id"),
        "chunk_index": chunk_index,
        "content": content,
        "score": score,
    }
    if isinstance(chunk, dict):
        payload.update({
            "chunk_id": chunk.get("id"),
            "course_id": chunk.get("course_id"),
            "course_title": chunk.get("course_title") or "",
            "chapter_id": chunk.get("chapter_id"),
            "chapter": chunk.get("chapter") or "",
            "knowledge_point_id": chunk.get("knowledge_point_id"),
            "knowledge_point": chunk.get("knowledge_point") or "",
            "section": chunk.get("section") or "",
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "content_hash": chunk.get("content_hash"),
            "vector_ref": chunk.get("vector_ref") or "",
        })
    return payload


def _result_identity(result: dict) -> tuple:
    return (
        result.get("chunk_id"),
        result.get("document_id"),
        result.get("chunk_index"),
        result.get("content_hash"),
        result.get("title"),
    )


def format_source_citation(source: dict) -> str:
    parts = []
    if source.get("course_title"):
        parts.append(f"课程：{source['course_title']}")
    if source.get("chapter"):
        parts.append(f"章节：{source['chapter']}")
    if source.get("section"):
        parts.append(f"小节：{source['section']}")
    page_start = source.get("page_start")
    page_end = source.get("page_end")
    if page_start:
        page_text = str(page_start)
        if page_end and page_end != page_start:
            page_text = f"{page_start}-{page_end}"
        parts.append(f"物理页：{page_text}")
    filename = source.get("source_filename") or source.get("title")
    if filename:
        parts.append(f"文档：{filename}")
    return "，".join(parts) or "来源元数据缺失"


def hybrid_query_chunks(question: str, documents: list[dict], user_id: int, limit: int = 4,
                         mode: str = "standard", timeout_ms: int = 3000) -> list[dict]:
    """混合检索：FAISS 语义向量检索优先，关键词检索回退

    支持 RAG 模式分级：
      - light: 仅关键词检索，速度优先
      - standard: FAISS 优先，关键词回退（原有逻辑）
      - deep: FAISS + 关键词评分融合，覆盖率优先

    缓存支持：命中缓存直接返回，不重复执行 embedding / vector search / rerank
    超时支持：超过 timeout_ms 返回空列表

    Args:
        question: 用户问题
        documents: 文档字典列表
        user_id: 用户 ID
        limit: 返回结果数量上限
        mode: RAG 模式 (light/standard/deep)
        timeout_ms: 超时时间（毫秒）

    Returns:
        检索结果列表（包含 title/content/score）
    """
    from app.services.rag_config import  ENABLE_RAG_OPTIMIZATION, ENABLE_RAG_CACHE, ENABLE_RAG_TIMING_LOG

    # 缓存检查
    if ENABLE_RAG_CACHE:
        from app.services.rag_config import  ragCacheGet
        cached = ragCacheGet(user_id, question, "hybrid_query", mode)
        if cached is not None:
            return cached

    # 计时
    _t0 = time.time()

    def _do_search() -> list[dict]:
        """实际执行检索（根据 mode 选择不同策略）"""
        if mode == "light" or not ENABLE_RAG_OPTIMIZATION:
            # light 模式：仅关键词检索，跳过 FAISS
            return query_chunks(question, documents, limit=min(limit, 3))
        elif mode == "deep":
            # deep 模式：FAISS + 关键词评分融合，提高覆盖率
            from .vector_store import search_user_index
            vector_results = search_user_index(user_id, question, limit)
            kw_results = query_chunks(question, documents, limit=limit)
            # 融合：向量结果优先，关键词结果补充
            seen_results = set()
            fused = []
            for r in (vector_results or []):
                identity = _result_identity(r)
                if identity not in seen_results:
                    fused.append(r)
                    seen_results.add(identity)
            for r in kw_results:
                identity = _result_identity(r)
                if identity not in seen_results:
                    fused.append(r)
                    seen_results.add(identity)
            return fused[:limit]
        else:
            # standard 模式：原有逻辑（FAISS 优先，关键词回退）
            from .vector_store import search_user_index
            vector_results = search_user_index(user_id, question, limit)
            if vector_results is not None:
                return vector_results
            return query_chunks(question, documents, limit)

    # 超时包装
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_do_search)
            results = future.result(timeout=timeout_ms / 1000)
    except TimeoutError:
        # 超时返回空结果
        if ENABLE_RAG_TIMING_LOG:
            import sys
            print(f"[rag_timing] hybrid_query_chunks TIMEOUT after {timeout_ms}ms | mode={mode} | question={question[:60]}",
                  file=sys.stderr, flush=True)
        results = []
    except Exception as exc:
        import sys
        print(f"[rag_timing] hybrid_query_chunks ERROR: {exc}", file=sys.stderr, flush=True)
        results = []

    # 写入缓存
    if ENABLE_RAG_CACHE and results:
        from app.services.rag_config import  ragCacheSet
        ragCacheSet(user_id, question, "hybrid_query", mode, "auto", results)

    # 计时日志
    if ENABLE_RAG_TIMING_LOG:
        elapsed_ms = round((time.time() - _t0) * 1000, 1)
        import sys
        print(f"[rag_timing] hybrid_query_chunks done | mode={mode} | elapsed_ms={elapsed_ms} | results={len(results)} | limit={limit}",
              file=sys.stderr, flush=True)

    return results
