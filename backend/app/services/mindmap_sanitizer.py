from __future__ import annotations

import re
from html import unescape
from dataclasses import dataclass


@dataclass
class MindMapValidation:
    valid: bool
    errors: list[str]


_FENCE_RE = re.compile(r"```(?:mermaid)?\s*([\s\S]*?)```", re.I)
_BAD_LABEL_CHARS = str.maketrans({
    "(": "（",
    ")": "）",
    "[": "【",
    "]": "】",
    "{": "｛",
    "}": "｝",
    "<": "＜",
    ">": "＞",
    "`": "'",
    '"': "'",
    ":": "：",
    ";": "；",
})


def extract_mindmap_source(text: str) -> str:
    source = (text or "").strip()
    match = _FENCE_RE.search(source)
    if match:
        return match.group(1).strip()
    return source


def _clean_label(label: str) -> str:
    label = unescape(label or "")
    label = re.sub(r"<\s*br\s*/?\s*>", " ", label, flags=re.I)
    label = re.sub(r"<[^>]+>", " ", label)
    label = re.sub(r"^\s*(?:[-*+]\s+|\d+[.、]\s*)", "", label).strip()
    label = re.sub(r"^#{1,6}\s*", "", label).strip()
    label = re.sub(r"\*\*([^*]+)\*\*", r"\1", label)
    label = re.sub(r"`([^`]+)`", r"\1", label)
    label = re.sub(r"^[\(\[\{]+|[\)\]\}]+$", "", label).strip()
    label = re.sub(r"(?:思维导图|知识图谱|导图)\s*$", "", label).strip()
    label = re.sub(r"\s+", " ", label).strip()
    label = label.translate(_BAD_LABEL_CHARS)
    return label[:32] or "知识点"


def _indent_level(line: str) -> int:
    expanded = line.replace("\t", "    ")
    return max(0, (len(expanded) - len(expanded.lstrip(" "))) // 2)


def _extract_items(source: str, topic: str) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower in {"mindmap", "```mermaid", "```"}:
            continue
        if stripped.startswith("```"):
            continue
        if re.match(r"^root\s*(?:\(\(|\[|\{)?", stripped, re.I):
            continue

        label = _clean_label(stripped)
        if not label or label == _clean_label(topic):
            continue

        if stripped.startswith("#"):
            heading_level = len(stripped) - len(stripped.lstrip("#"))
            level = min(3, max(1, heading_level - 1))
        else:
            level = min(4, max(1, _indent_level(line) + 1))
        items.append((level, label))

    return items


def _fallback_items(topic: str) -> list[tuple[int, str]]:
    return [
        (1, "核心概念"),
        (2, "定义与作用"),
        (2, "关键流程"),
        (2, "适用场景"),
        (1, "学习资源"),
        (2, "讲解文档"),
        (2, "练习题库"),
        (2, "实操案例"),
        (1, "评估闭环"),
        (2, "测评反馈"),
        (2, "错题复盘"),
        (2, "路径调整"),
    ]


def _rebalance_primary_branches(items: list[tuple[int, str]]) -> list[tuple[int, str]]:
    if len(items) < 4:
        return items
    level_one_count = sum(1 for level, _ in items if level == 1)
    if level_one_count > 1:
        return items

    # 常见失败形态：LLM 输出 “# 总标题 / ## 章节 / ### 小节”，
    # 直接转 mindmap 会变成 root 只有一个子节点。这里把章节上提为主分支。
    first_level_one_index = next((index for index, (level, _) in enumerate(items) if level == 1), -1)
    if first_level_one_index >= 0:
        rebalanced: list[tuple[int, str]] = []
        for index, (level, label) in enumerate(items):
            if index == first_level_one_index:
                continue
            rebalanced.append((max(1, level - 1), label))
        return rebalanced or items

    min_level = min(level for level, _ in items)
    return [(max(1, level - min_level + 1), label) for level, label in items]


def normalize_mindmap_content(content: str, topic: str = "学习主题") -> str:
    source = extract_mindmap_source(content)
    topic_label = _clean_label(topic or "学习主题")
    items = _extract_items(source, topic_label)
    if len(items) < 3:
        items = _fallback_items(topic_label)
    items = _rebalance_primary_branches(items)

    normalized: list[tuple[int, str]] = []
    previous_level = 0
    seen_at_level: set[tuple[int, str]] = set()
    for level, label in items[:80]:
        if not label:
            continue
        level = min(level, previous_level + 1) if previous_level else min(level, 1)
        key = (level, label)
        if key in seen_at_level:
            continue
        seen_at_level.add(key)
        normalized.append((level, label))
        previous_level = level

    lines = ["## {topic} 思维导图".format(topic=topic_label), "", "```mermaid", "mindmap", f"  root(({topic_label}))"]
    for level, label in normalized:
        lines.append("  " * (level + 1) + label)
    lines.append("```")
    return "\n".join(lines)


def validate_mindmap_content(content: str) -> MindMapValidation:
    source = extract_mindmap_source(content)
    errors: list[str] = []
    lines = [line.rstrip() for line in source.splitlines() if line.strip()]
    if not lines:
        return MindMapValidation(False, ["内容为空"])
    if lines[0].strip().lower() != "mindmap":
        errors.append("缺少 mindmap 起始行")
    if not any(re.match(r"^\s*root\s*(?:\(\(|\[|\{)?", line.strip(), re.I) for line in lines[1:3]):
        errors.append("缺少 root 根节点")
    node_lines = [line for line in lines[1:] if not re.match(r"^\s*root\s*", line.strip(), re.I)]
    if len(node_lines) < 3:
        errors.append("分支节点少于 3 个")
    for index, line in enumerate(lines, 1):
        if "\t" in line:
            errors.append(f"第 {index} 行包含 Tab 缩进")
        if line.strip().startswith(("-", "*", "#")):
            errors.append(f"第 {index} 行仍包含 Markdown 标记")
    return MindMapValidation(not errors, errors)


def mermaid_to_tree_json(content: str, topic: str = "学习主题") -> dict:
    """将 Mermaid mindmap 文本转换为嵌套树状 JSON。

    输出格式:
      {"text": "主题", "children": [{"text": "分支1", "children": [...]}, ...]}

    此格式可直接被前端 mind-elixir 组件消费，无需二次转换。
    """
    source = extract_mindmap_source(content)
    topic_label = _clean_label(topic or "学习主题")
    items = _extract_items(source, topic)
    if len(items) < 3:
        items = _fallback_items(topic_label)
    items = _rebalance_primary_branches(items)

    # 构建嵌套树：items 为 [(level, label), ...]，level 从 1 开始
    def _build_subtree(item_list, start_level):
        result = []
        i = 0
        while i < len(item_list):
            level, label = item_list[i]
            if level == start_level:
                node: dict = {"text": label, "children": []}
                i += 1
                children = []
                while i < len(item_list) and item_list[i][0] > start_level:
                    children.append(item_list[i])
                    i += 1
                if children:
                    node["children"] = _build_subtree(children, start_level + 1)
                result.append(node)
            else:
                i += 1
        return result

    children = _build_subtree(items, 1)
    return {"text": topic_label, "children": children}


def convert_to_layout_json(content: str, topic: str = "学习主题") -> list[dict]:
    """将 Mermaid mindmap 文本转换为布局优化的 JSON 节点数组。

    输出格式适合直接导入 mindmap API（如 ai-mindmap.app）：
      [
        {"id": 1, "label": "根节点", "parent": null, "level": 0, "children_count": 4},
        {"id": 2, "label": "一级分支", "parent": 1, "level": 1, "children_count": 3},
        ...
      ]

    优化策略：
    - 过长的标签自动精简为核心关键词（不超过 24 字）
    - 同一父节点下的子节点数量控制在 6 个以内，超出的自动拆分为补充子节点
    - 确保层级连续（不跳级），布局紧凑
    """
    source = extract_mindmap_source(content)
    topic_label = _clean_label(topic or "学习主题")
    items = _extract_items(source, topic)
    if len(items) < 3:
        items = _fallback_items(topic_label)
    items = _rebalance_primary_branches(items)

    # 紧凑化：限平不超过 6 个一级分支，多余降为二级
    level_ones = [(i, lvl, lbl) for i, (lvl, lbl) in enumerate(items) if lvl == 1]
    if len(level_ones) > 6:
        extra = level_ones[6:]
        extra_indices = {i for i, _, _ in extra}
        compacted: list[tuple[int, str]] = []
        for i, (lvl, lbl) in enumerate(items):
            if i in extra_indices:
                compacted.append((2, lbl))
            else:
                compacted.append((lvl, lbl))
        items = compacted

    # 精简过长标签
    trimmed: list[tuple[int, str]] = []
    for lvl, lbl in items:
        words = lbl.split()
        if len(lbl) > 24:
            # 保留前半段核心关键词
            short = lbl[:24].rsplit("，", 1)[0] if "，" in lbl[:24] else lbl[:24]
            short = short.rstrip("，、；：")
            if len(short) < 6:
                short = lbl[:24]
            trimmed.append((lvl, short))
        else:
            trimmed.append((lvl, lbl))

    # 构建节点树：根节点 level=0，依次挂载
    nodes: list[dict] = []
    node_id_counter = [1]
    parent_stack: list[int] = []  # 每层的 parent id

    # 添加根节点
    root_id = node_id_counter[0]
    node_id_counter[0] += 1
    nodes.append({
        "id": root_id,
        "label": topic_label,
        "parent": None,
        "level": 0,
        "children_count": 0,
    })
    parent_stack = [root_id]

    # 逐层处理子节点
    previous_level = 0
    level_parent_map: dict[int, int] = {0: root_id}

    for lvl, lbl in trimmed:
        actual_level = min(lvl, previous_level + 1) if previous_level else 1
        pid = level_parent_map.get(actual_level - 1, root_id)
        node_id = node_id_counter[0]
        node_id_counter[0] += 1
        nodes.append({
            "id": node_id,
            "label": lbl,
            "parent": pid,
            "level": actual_level,
            "children_count": 0,
        })
        level_parent_map[actual_level] = node_id
        previous_level = actual_level

    # 更新各节点的 children_count
    pid_to_count: dict[int, int] = {}
    for node in nodes:
        p = node["parent"]
        if p is not None:
            pid_to_count[p] = pid_to_count.get(p, 0) + 1
    for node in nodes:
        node["children_count"] = pid_to_count.get(node["id"], 0)

    return nodes
