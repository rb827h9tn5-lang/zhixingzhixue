from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = None
_EMBEDDING_MODEL_LOCK = threading.Lock()
_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_INDEX_CACHE: dict[int, tuple[Any, list[dict]]] = {}


def _get_vector_dir() -> Path:
    from flask import current_app

    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
    vector_dir = Path(upload_folder) / "vector_index"
    vector_dir.mkdir(parents=True, exist_ok=True)
    return vector_dir


def _index_path(user_id: int) -> Path:
    return _get_vector_dir() / f"user_{user_id}.index"


def _meta_path(user_id: int) -> Path:
    return _get_vector_dir() / f"user_{user_id}_meta.json"


def get_embedding_model():
    """占位符 — 已切换至远程 API 模式"""
    return None


def _generate_embeddings_api(texts: list[str]) -> np.ndarray | None:
    """通过 DashScope API 生成嵌入向量（自动分批，每批最多 10 条）"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    model = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "")
    if not api_key or not model:
        return None
    if not texts:
        return None

    try:
        import requests

        endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
        # text-embedding-v3 限制每批最多 10 条
        batch_size = 10
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": batch,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            batch_embeddings = [item["embedding"] for item in sorted_data]
            all_embeddings.extend(batch_embeddings)

        result = np.array(all_embeddings, dtype=np.float32)

        # L2 归一化（兼容 FAISS IndexFlatIP）
        norms = np.linalg.norm(result, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        result /= norms

        logger.info("DashScope 嵌入 API 调用成功，模型: %s，向量维度: %s，总条数: %s", model, result.shape[1], len(texts))
        return result
    except Exception as exc:
        resp_body = ""
        if hasattr(exc, "response") and exc.response is not None:
            try:
                resp_body = exc.response.text[:500]
            except Exception:
                pass
        logger.warning("DashScope 嵌入 API 调用失败: %s%s，将回退关键词检索", exc, f" | 响应: {resp_body}" if resp_body else "")
        return None


def generate_embeddings(texts: list[str]) -> np.ndarray | None:
    """通过 DashScope API 生成归一化嵌入向量"""
    return _generate_embeddings_api(texts)


def rebuild_user_index(user_id: int, documents: list[dict]) -> bool:
    """根据用户所有文档的分块重建 FAISS 索引

    参数:
        user_id: 用户 ID
        documents: 文档字典列表，每项需包含 title 和 chunks 字段

    返回:
        是否成功重建（False 表示回退到关键词检索）
    """
    all_chunks = []
    all_metadata = []

    for doc in documents:
        structured_chunks = doc.get("structured_chunks") or []
        chunks = structured_chunks or doc.get("chunks") or []
        for index, chunk in enumerate(chunks):
            chunk_text = (
                (chunk.get("chunk_text") or chunk.get("content") or "").strip()
                if isinstance(chunk, dict)
                else chunk.strip() if isinstance(chunk, str) else ""
            )
            if chunk_text:
                all_chunks.append(chunk_text)
                metadata = {
                    "title": doc.get("title", "未命名"),
                    "source_filename": doc.get("source_filename") or doc.get("title", "未命名"),
                    "document_id": doc.get("id"),
                    "content": chunk_text,
                    "chunk_index": index,
                }
                if isinstance(chunk, dict):
                    metadata.update({
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
                all_metadata.append(metadata)

    if not all_chunks:
        _save_empty_index(user_id)
        return True

    import faiss

    embeddings = generate_embeddings(all_chunks)
    if embeddings is None:
        return False

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    _save_index(user_id, index, all_metadata)
    _INDEX_CACHE.pop(user_id, None)
    logger.info("用户 %s 的 FAISS 索引重建完成，共 %s 个分块", user_id, len(all_chunks))
    return True


def search_user_index(user_id: int, query: str, limit: int = 4) -> list[dict] | None:
    """在用户的 FAISS 索引中执行语义搜索

    参数:
        user_id: 用户 ID
        query: 搜索问题
        limit: 返回结果数量上限

    返回:
        搜索结果列表（包含 title/content/score），检索失败或索引为空时返回 None
    """
    index, metadata = _load_index(user_id)
    if index is None or index.ntotal == 0:
        return None
    if not metadata:
        return None

    import faiss

    query_embedding = generate_embeddings([query])
    if query_embedding is None:
        return None

    k = min(limit, index.ntotal)
    scores, indices = index.search(query_embedding, k)

    results = []
    for i in range(k):
        idx = int(indices[0][i])
        if idx >= 0 and idx < len(metadata):
            score = float(scores[0][i])
            if score > 0:
                result = dict(metadata[idx])
                result["score"] = round(score, 4)
                results.append(result)

    return results if results else None


def _save_index(user_id: int, index, metadata: list[dict]):
    """保存 FAISS 索引和元数据到磁盘"""
    import faiss

    index_path = _index_path(user_id)
    meta_path = _meta_path(user_id)

    faiss.write_index(index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)


def _save_empty_index(user_id: int):
    """保存空标记（表示该用户无文档，并非索引损坏）"""
    index_path = _index_path(user_id)
    meta_path = _meta_path(user_id)

    if index_path.exists():
        index_path.unlink()
    empty_marker = {"empty": True, "user_id": user_id}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(empty_marker, f, ensure_ascii=False)
    _INDEX_CACHE.pop(user_id, None)


def _load_index(user_id: int) -> tuple:
    """从磁盘加载 FAISS 索引和元数据（带内存缓存）"""
    if user_id in _INDEX_CACHE:
        return _INDEX_CACHE[user_id]

    import faiss

    index_path = _index_path(user_id)
    meta_path = _meta_path(user_id)

    if not index_path.exists() or not meta_path.exists():
        _INDEX_CACHE[user_id] = (None, [])
        return None, []

    try:
        meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(meta_data, dict) and meta_data.get("empty"):
            _INDEX_CACHE[user_id] = (None, [])
            return None, []

        index = faiss.read_index(str(index_path))
        result = (index, meta_data)
        _INDEX_CACHE[user_id] = result
        return result
    except Exception as exc:
        logger.error("加载 FAISS 索引失败（用户 %s）: %s", user_id, exc)
        _INDEX_CACHE[user_id] = (None, [])
        return None, []


def clear_user_index(user_id: int):
    """清除用户的 FAISS 索引缓存和磁盘文件"""
    _INDEX_CACHE.pop(user_id, None)
    index_path = _index_path(user_id)
    meta_path = _meta_path(user_id)
    if index_path.exists():
        index_path.unlink()
    if meta_path.exists():
        meta_path.unlink()
