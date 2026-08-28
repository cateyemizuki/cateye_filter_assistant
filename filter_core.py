"""不要只说不干 — 核心逻辑（纯 Python，不依赖 MaiBot SDK，便于单元测试）。

职责：
- 识别序列化后的 Context Item 中属于「assistant 角色」的项；
- 按配置开关过滤：去掉纯文本 assistant 消息（AssistantMessageItem）与
  推理内容（ReasoningItem），保留 system / user / tool（函数调用与结果）相关项；
- 兼容两种载荷形态：
  1. MaiBot Context Item 快照（``item_type`` 区分角色，``maisaka.planner.before_request``
     的 ``items`` 载荷即此形态）；
  2. OpenAI 风格 ``messages`` 数组（``role`` 字段区分角色），作为兼容兜底。

设计要点：
- 只过滤「纯文本 assistant 消息」与「推理内容」（正是 DeepSeek V4 系列模型中
  包含「决策：保持安静，不回复、不调用工具」等负面示范、污染工具调用分布的项）；
- **必须保留** ``FunctionCallItem``（assistant 工具调用）与
  ``FunctionCallOutputItem``（tool 结果）——二者是协议原子段，删除调用段会使
  结果段变成「孤儿 function output」，MaiBot 的 ``validate_context_items`` 会拒绝
  该修改（Hook 改写被整体忽略）。保留工具调用对既满足「仅保留 system/user/tool 角色」
  的需求（tool 结果即 tool 角色），又不破坏协议约束。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

# 纯文本 assistant 消息（问题根源：含「不调用工具」坏示例）
TYPE_ASSISTANT_MESSAGE = "AssistantMessageItem"
# 推理内容（assistant 思考，同样可能含负面示范）
TYPE_REASONING = "ReasoningItem"
# 工具调用（assistant tool_calls；必须保留，与 tool 结果成对）
TYPE_FUNCTION_CALL = "FunctionCallItem"
# tool 结果（tool 角色；必须保留）
TYPE_FUNCTION_CALL_OUTPUT = "FunctionCallOutputItem"
# system 角色
TYPE_SYSTEM_MESSAGE = "SystemMessageItem"
# user 角色
TYPE_USER_MESSAGE = "UserMessageItem"


def classify_item(item: Any) -> str:
    """返回单个 Context Item / 消息 dict 的角色类别键。

    优先按 ``item_type`` 识别（MaiBot Context Item 快照），
    否则回退按 ``role`` 识别（OpenAI 风格 messages 数组）。

    返回值：``"assistant"`` / ``"reasoning"`` / ``"tool_call"`` / ``"tool_result"`` /
    ``"system"`` / ``"user"`` / ``"unknown"``。
    """
    if not isinstance(item, dict):
        return "unknown"

    item_type = item.get("item_type")
    if isinstance(item_type, str) and item_type:
        if item_type == TYPE_ASSISTANT_MESSAGE:
            return "assistant"
        if item_type == TYPE_REASONING:
            return "reasoning"
        if item_type == TYPE_FUNCTION_CALL:
            return "tool_call"
        if item_type == TYPE_FUNCTION_CALL_OUTPUT:
            return "tool_result"
        if item_type == TYPE_SYSTEM_MESSAGE:
            return "system"
        if item_type == TYPE_USER_MESSAGE:
            return "user"
        # 其它已知 Item 类型（ProviderActivityItem / ProviderOpaqueItem 等）不属 assistant
        return "unknown"

    role = item.get("role")
    if isinstance(role, str):
        role = role.strip().lower()
        if role == "assistant":
            # OpenAI 风格 messages：assistant 消息若带 tool_calls 是工具调用段（保留），
            # 否则是纯文本（过滤）
            tool_calls = item.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                return "tool_call"
            return "assistant"
        if role == "tool":
            return "tool_result"
        if role == "system":
            return "system"
        if role == "user":
            return "user"
    return "unknown"


def strip_assistant_items(
    items: Sequence[Any],
    *,
    strip_assistant_messages: bool = True,
    strip_reasoning_messages: bool = True,
) -> Dict[str, Any]:
    """过滤掉 items 中的 assistant 纯文本消息与推理内容。

    参数：
        items: 即将发送给 LLM 的消息 / Context Item 列表。
        strip_assistant_messages: 是否过滤纯文本 assistant 消息（默认 True）。
        strip_reasoning_messages: 是否过滤推理内容 ReasoningItem（默认 True）。

    返回：
        ``{"items": [...], "removed": int}`` — 过滤后的列表与被移除的条数。
        未过滤任何项时 ``items`` 仍返回原列表对象（便于上层判断是否变化）。
    """
    if not isinstance(items, list):
        return {"items": list(items) if items is not None else [], "removed": 0}

    kept: List[Any] = []
    removed = 0
    for item in items:
        category = classify_item(item)
        drop = False
        if category == "assistant":
            drop = strip_assistant_messages
        elif category == "reasoning":
            drop = strip_reasoning_messages
        if drop:
            removed += 1
            continue
        kept.append(item)

    if removed == 0:
        return {"items": items, "removed": 0}
    return {"items": kept, "removed": removed}
