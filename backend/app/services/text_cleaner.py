# -*- coding: utf-8 -*-
"""
文本清洗与质量检测工具函数。

在文档解析 -> 入库的全流程中，用于：
1. 清洗提取文本（去乱码、去控制字符、规范化）
2. 检测坏文本（乱码比例、有效字符比例）
3. 检测目录页/页眉页脚（避免入库）
"""
from __future__ import annotations

import re
import unicodedata

# Unicode 替换字符常量（用于匹配乱码）
REPLACEMENT_CHAR = "�"


def clean_extracted_text(text: str) -> str:
    """清洗 PDF / DOCX 提取的原始文本。

    处理流程：
    1. Unicode 规范化（NFKC）
    2. 删除 Unicode 替换字符
    3. 删除不可见控制字符
    4. 删除目录点线引导符
    5. 删除异常重复符号
    6. 合并多余空白
    7. 修剪首尾空白
    """
    if not text:
        return ""

    # 1. Unicode 规范化
    text = unicodedata.normalize("NFKC", text)

    # 2. 删除 Unicode 替换字符
    text = text.replace(REPLACEMENT_CHAR, "")

    # 3. 删除常见不可见控制字符（保留 \t \n \r）
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # 4. 删除目录中的点线 / 引导线（连续 5 个以上）
    text = re.sub(r"[\.·。…_—-]{5,}", " ", text)

    # 5. 删除连续 2 个以上的替换字符
    text = re.sub(REPLACEMENT_CHAR + r"{2,}", "", text)

    # 6. 合并空白（保留换行）
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def is_bad_text(text: str) -> bool:
    """检测文本是否为坏文本，应丢弃。

    规则：
    1. 文本过短（< 20 字符）
    2. 包含大量替换字符
    3. 有效中文 / 英文 / 数字字符比例过低
    """
    if not text or len(text.strip()) < 20:
        return True

    total_len = max(len(text), 1)
    bad_char_count = text.count(REPLACEMENT_CHAR)
    bad_ratio = bad_char_count / total_len

    # 乱码比例 > 1% 则丢弃
    if bad_ratio > 0.01:
        return True

    # 有效字符（中文 / 英文 / 数字）比例 < 25% 则丢弃
    valid_chars = re.findall(r"[一-鿿A-Za-z0-9]", text)
    valid_ratio = len(valid_chars) / total_len
    if valid_ratio < 0.25:
        return True

    return False


def is_toc_like_text(text: str) -> bool:
    """检测文本是否为目录页，目录页不应该入库。

    特征：
    1. 前 200 字符包含"目录"
    2. 大量章节编号（如 4.6.5、5.1）
    3. 大量行尾页码
    4. 大量点线引导符
    5. 文本结构类似：标题 + 点线 + 页码
    """
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    toc_score = 0

    # 特征 1：包含"目录"关键词
    if "目录" in text[:200]:
        toc_score += 2

    # 特征 2：章节编号行的比例
    chapter_lines = sum(
        1 for line in lines
        if re.search(r"^\s*\d+(\.\d+)+\s+", line)
    )
    if chapter_lines >= 5:
        toc_score += 2

    # 特征 3：行尾页码的比例
    page_number_lines = sum(
        1 for line in lines
        if re.search(r"\s\d{1,4}$", line)
    )
    if page_number_lines / max(len(lines), 1) > 0.4:
        toc_score += 2

    # 特征 4：点线引导符的行数
    dot_leader_lines = sum(
        1 for line in lines
        if re.search(r"[\.·。…_—-]{5,}", line)
    )
    if dot_leader_lines >= 3:
        toc_score += 2

    # 特征 5：文本行数较少，但每行都很短（目录特征）
    short_lines = sum(1 for line in lines if len(line) < 30)
    if len(lines) >= 10 and short_lines / max(len(lines), 1) > 0.6:
        toc_score += 1

    return toc_score >= 3


def is_header_footer_like(text: str) -> bool:
    """检测文本是否为页眉/页脚片段，此类片段应丢弃。

    特征：
    1. 纯数字页码行
    2. 包含"第 X 页"模式
    3. 仅包含章节标题且长度很短（页眉）
    """
    if not text or len(text.strip()) < 3:
        return True

    stripped = text.strip()
    # 纯数字（页码）
    if re.fullmatch(r"\d{1,4}", stripped):
        return True
    # "第 X 页"、"Page X"
    if re.search(r"^(第\s*\d+\s*页|Page\s*\d+)$", stripped, re.IGNORECASE):
        return True
    # 极短的重复性文字（页眉的可能）
    if len(stripped) < 15 and re.search(r"^(第.*章|Chapter|\d+\.\d+)\s*", stripped):
        return True

    return False


def filter_document_pages(pages: list[dict]) -> list[dict]:
    """逐页过滤：清洗 -> 坏文本检测 -> 目录页检测 -> 页眉页脚检测。

    Args:
        pages: [{"page": 1, "text": "..."}, ...]

    Returns:
        清洗后通过检测的有效页列表
    """
    valid_pages = []
    for page in pages:
        raw_text = page.get("text") or ""

        # 空页跳过
        if not raw_text.strip():
            continue

        # 目录页检测
        if is_toc_like_text(raw_text):
            continue

        # 清洗
        clean_text = clean_extracted_text(raw_text)

        # 坏文本检测
        if is_bad_text(clean_text):
            continue

        # 如果清洗后为空，跳过
        if not clean_text:
            continue

        valid_pages.append({"page": page["page"], "text": clean_text})

    return valid_pages


def filter_chunks(chunks: list[str]) -> list[str]:
    """对已切分的 chunk 列表进行逐块过滤。

    每个 chunk 经过：清洗 -> 坏文本检测 -> 页眉页脚检测。
    """
    valid_chunks = []
    for chunk in chunks:
        cleaned = clean_extracted_text(chunk)
        if is_bad_text(cleaned):
            continue
        if is_header_footer_like(cleaned):
            continue
        if not cleaned:
            continue
        valid_chunks.append(cleaned)
    return valid_chunks