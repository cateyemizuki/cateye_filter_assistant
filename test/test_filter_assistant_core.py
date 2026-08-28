# -*- coding: utf-8 -*-
"""不要只说不干 — 核心逻辑单元测试（filter_core.py，不依赖 SDK）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cateye_filter_assistant"))

from filter_core import (  # noqa: E402
    classify_item,
    strip_assistant_items,
    TYPE_ASSISTANT_MESSAGE,
    TYPE_FUNCTION_CALL,
    TYPE_FUNCTION_CALL_OUTPUT,
    TYPE_REASONING,
    TYPE_SYSTEM_MESSAGE,
    TYPE_USER_MESSAGE,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def ctx_item(item_type, item_id="i1", logical_turn_id=None):
    """构造一个 MaiBot Context Item 快照字典。"""
    meta = {"item_id": item_id, "logical_turn_id": logical_turn_id, "timestamp": "2026-08-27T00:00:00+08:00"}
    return {"item_type": item_type, "meta": meta, "parts": []}


def openai_msg(role, content="", tool_calls=None, tool_call_id=None):
    """构造一个 OpenAI 风格 messages 数组元素。"""
    msg = {"role": role, "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    if tool_call_id is not None:
        msg["tool_call_id"] = tool_call_id
    return msg


def main():
    print("== classify_item：Context Item 快照 ==")
    check("AssistantMessageItem → assistant",
          classify_item(ctx_item(TYPE_ASSISTANT_MESSAGE)) == "assistant")
    check("ReasoningItem → reasoning",
          classify_item(ctx_item(TYPE_REASONING)) == "reasoning")
    check("FunctionCallItem → tool_call",
          classify_item(ctx_item(TYPE_FUNCTION_CALL)) == "tool_call")
    check("FunctionCallOutputItem → tool_result",
          classify_item(ctx_item(TYPE_FUNCTION_CALL_OUTPUT)) == "tool_result")
    check("SystemMessageItem → system",
          classify_item(ctx_item(TYPE_SYSTEM_MESSAGE)) == "system")
    check("UserMessageItem → user",
          classify_item(ctx_item(TYPE_USER_MESSAGE)) == "user")
    check("未知 item_type → unknown",
          classify_item(ctx_item("ProviderActivityItem")) == "unknown")
    check("非 dict → unknown", classify_item("not a dict") == "unknown")
    check("None → unknown", classify_item(None) == "unknown")

    print("== classify_item：OpenAI 风格 messages ==")
    check("role=system → system", classify_item(openai_msg("system")) == "system")
    check("role=user → user", classify_item(openai_msg("user")) == "user")
    check("role=tool → tool_result", classify_item(openai_msg("tool", tool_call_id="c1")) == "tool_result")
    check("role=assistant 纯文本 → assistant",
          classify_item(openai_msg("assistant", content="决策：保持安静")) == "assistant")
    check("role=assistant 带 tool_calls → tool_call（保留）",
          classify_item(openai_msg("assistant", content="", tool_calls=[{"id": "c1"}])) == "tool_call")
    check("role 大小写不敏感",
          classify_item(openai_msg("ASSISTANT", content="x")) == "assistant")
    check("role=unknown → unknown", classify_item(openai_msg("developer")) == "unknown")

    print("== strip_assistant_items：Context Item 快照 ==")
    items = [
        ctx_item(TYPE_SYSTEM_MESSAGE, "s1"),
        ctx_item(TYPE_USER_MESSAGE, "u1"),
        ctx_item(TYPE_ASSISTANT_MESSAGE, "a1"),
        ctx_item(TYPE_ASSISTANT_MESSAGE, "a2"),
        ctx_item(TYPE_FUNCTION_CALL, "f1"),
        ctx_item(TYPE_FUNCTION_CALL_OUTPUT, "f2"),
        ctx_item(TYPE_REASONING, "r1"),
    ]
    res = strip_assistant_items(items)
    check("移除 2 条 assistant + 1 条 reasoning", res["removed"] == 3, str(res["removed"]))
    check("保留 system", res["items"][0]["item_type"] == TYPE_SYSTEM_MESSAGE)
    check("保留 user", res["items"][1]["item_type"] == TYPE_USER_MESSAGE)
    check("保留 FunctionCallItem", res["items"][2]["item_type"] == TYPE_FUNCTION_CALL)
    check("保留 FunctionCallOutputItem", res["items"][3]["item_type"] == TYPE_FUNCTION_CALL_OUTPUT)
    check("无 assistant / reasoning 残留",
          not any(i["item_type"] in (TYPE_ASSISTANT_MESSAGE, TYPE_REASONING) for i in res["items"]))
    check("顺序保持", [i["item_type"] for i in res["items"]] ==
          [TYPE_SYSTEM_MESSAGE, TYPE_USER_MESSAGE, TYPE_FUNCTION_CALL, TYPE_FUNCTION_CALL_OUTPUT])

    print("== strip_assistant_items：开关控制 ==")
    res2 = strip_assistant_items(items, strip_assistant_messages=False)
    check("关闭 assistant 开关 → 只移除 reasoning", res2["removed"] == 1, str(res2["removed"]))
    res3 = strip_assistant_items(items, strip_reasoning_messages=False)
    check("关闭 reasoning 开关 → 只移除 assistant", res3["removed"] == 2, str(res3["removed"]))
    res4 = strip_assistant_items(items, strip_assistant_messages=False, strip_reasoning_messages=False)
    check("两个开关都关 → 不移除", res4["removed"] == 0 and res4["items"] is items)

    print("== strip_assistant_items：无过滤项时返回原列表 ==")
    clean = [ctx_item(TYPE_SYSTEM_MESSAGE, "s1"), ctx_item(TYPE_USER_MESSAGE, "u1"),
             ctx_item(TYPE_FUNCTION_CALL, "f1"), ctx_item(TYPE_FUNCTION_CALL_OUTPUT, "f2")]
    res5 = strip_assistant_items(clean)
    check("无 assistant → removed=0", res5["removed"] == 0)
    check("无 assistant → 返回原列表对象", res5["items"] is clean)

    print("== strip_assistant_items：OpenAI 风格 messages ==")
    msgs = [
        openai_msg("system", "你是助手"),
        openai_msg("user", "你好"),
        openai_msg("assistant", "决策：保持安静，不回复、不调用工具。"),
        openai_msg("assistant", "", tool_calls=[{"id": "c1", "function": {"name": "reply", "arguments": "{}"}}]),
        openai_msg("tool", "工具结果", tool_call_id="c1"),
    ]
    res6 = strip_assistant_items(msgs)
    check("移除纯文本 assistant（1 条）", res6["removed"] == 1, str(res6["removed"]))
    check("保留带 tool_calls 的 assistant 与 tool 结果", len(res6["items"]) == 4)
    check("tool 结果仍在", res6["items"][3]["role"] == "tool")

    print("== strip_assistant_items：边界 ==")
    check("None → 空列表", strip_assistant_items(None)["items"] == [])
    check("非列表（tuple）→ 转列表", isinstance(strip_assistant_items((1, 2))["items"], list))
    check("空列表 → removed=0", strip_assistant_items([])["removed"] == 0)

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
