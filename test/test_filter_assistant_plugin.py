# -*- coding: utf-8 -*-
"""不要只说不干 — 插件类集成测试：用 stub SDK 加载 plugin.py，验证 Hook 过滤逻辑。"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "cateye_filter_assistant"))

# ---------- stub maibot_sdk ----------
import types  # noqa: E402

sdk = types.ModuleType("maibot_sdk")
CONFIG_RELOAD_SCOPE_SELF = "self"
sdk.CONFIG_RELOAD_SCOPE_SELF = CONFIG_RELOAD_SCOPE_SELF

# stub maibot_sdk.types
sdk_types = types.ModuleType("maibot_sdk.types")


class _StrEnum(str):
    pass


class HookMode(_StrEnum):
    BLOCKING = "blocking"
    OBSERVE = "observe"


class HookOrder(_StrEnum):
    EARLY = "early"
    NORMAL = "normal"
    LATE = "late"


class ErrorPolicy(_StrEnum):
    ABORT = "abort"
    SKIP = "skip"
    LOG = "log"


sdk_types.HookMode = HookMode
sdk_types.HookOrder = HookOrder
sdk_types.ErrorPolicy = ErrorPolicy
sys.modules["maibot_sdk.types"] = sdk_types


class Field:
    def __init__(self, default=None, default_factory=None, description="", json_schema_extra=None):
        self.default = default
        self.default_factory = default_factory
        self.description = description
        self.json_schema_extra = json_schema_extra


sdk.Field = Field


def HookHandler(hook, **kwargs):
    def deco(fn):
        fn._hook_name = hook
        fn._hook_kwargs = kwargs
        return fn
    return deco


sdk.HookHandler = HookHandler


class PluginConfigBase:
    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        cls.model_fields = dict(getattr(cls, "model_fields", {}))
        for name, ann in cls.__annotations__.items():
            if name.startswith("__"):
                continue
            attr = getattr(cls, name, None)
            if isinstance(attr, Field) and name not in cls.model_fields:
                cls.model_fields[name] = attr
        cls.__ui_label__ = kw.get("__ui_label__", getattr(cls, "__ui_label__", ""))
        cls.__ui_icon__ = kw.get("__ui_icon__", getattr(cls, "__ui_icon__", ""))
        cls.__ui_order__ = kw.get("__ui_order__", getattr(cls, "__ui_order__", 0))


sdk.PluginConfigBase = PluginConfigBase


class MaiBotPlugin:
    config_model = None
    config_reload_subscriptions = ()

    def __init__(self):
        self.ctx = types.SimpleNamespace(
            paths=types.SimpleNamespace(data_dir=os.path.join(ROOT, "data", "plugins", "x")),
            logger=types.SimpleNamespace(
                debug=lambda *a, **k: None,
                info=lambda *a, **k: print("[INFO]", *a),
                warning=lambda *a, **k: print("[WARN]", *a),
                error=lambda *a, **k: print("[ERROR]", *a),
            ),
        )
        self.config = self._make_default_config(self.config_model)
        self._plugin_config_data = {}

    def _make_default_config(self, model):
        def build(cls):
            obj = types.SimpleNamespace()
            for name, finfo in getattr(cls, "model_fields", {}).items():
                val = finfo.default_factory() if finfo.default_factory is not None else finfo.default
                if isinstance(val, PluginConfigBase):
                    setattr(obj, name, build(type(val)))
                elif isinstance(val, type) and issubclass(val, PluginConfigBase):
                    setattr(obj, name, build(val))
                else:
                    setattr(obj, name, val)
            return obj

        return build(model)

    async def on_load(self):
        raise NotImplementedError

    async def on_unload(self):
        raise NotImplementedError

    async def on_config_update(self, scope, config_data, version):
        raise NotImplementedError

    def get_plugin_config_data(self):
        return dict(getattr(self, "_plugin_config_data", {}))


sdk.MaiBotPlugin = MaiBotPlugin
sys.modules["maibot_sdk"] = sdk

# ---------- 导入插件 ----------
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "cateye_filter_assistant.plugin", os.path.join(ROOT, "cateye_filter_assistant", "plugin.py")
)
plugin = importlib.util.module_from_spec(spec)
sys.modules["cateye_filter_assistant.plugin"] = plugin
spec.loader.exec_module(plugin)

inst = plugin.create_plugin()

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


def ctx_item(item_type, item_id):
    meta = {"item_id": item_id, "logical_turn_id": None, "timestamp": "2026-08-27T00:00:00+08:00"}
    return {"item_type": item_type, "meta": meta, "parts": []}


def make_planner_kwargs(n_assistant=2, n_reasoning=1):
    """构造一个带若干 assistant 消息 / 推理内容的 planner hook kwargs。"""
    items = [
        ctx_item("SystemMessageItem", "s1"),
        ctx_item("UserMessageItem", "u1"),
    ]
    for i in range(n_assistant):
        items.append(ctx_item("AssistantMessageItem", f"a{i}"))
    items.append(ctx_item("FunctionCallItem", "f1"))
    items.append(ctx_item("FunctionCallOutputItem", "f2"))
    for i in range(n_reasoning):
        items.append(ctx_item("ReasoningItem", f"r{i}"))
    return {
        "items": items,
        "item_schema_version": 1,
        "tool_definitions": [],
        "selected_history_count": 8,
        "built_message_count": len(items),
        "selection_reason": "test",
        "session_id": "sess1",
    }


async def main() -> int:
    print("== 插件结构 ==")
    check("Hook 名是 maisaka.planner.before_request",
          getattr(inst.hook_strip_assistant, "_hook_name", "") == "maisaka.planner.before_request")
    check("Hook 模式 BLOCKING",
          getattr(inst.hook_strip_assistant, "_hook_kwargs", {}).get("mode") == HookMode.BLOCKING)
    check("Hook 错误策略 SKIP",
          getattr(inst.hook_strip_assistant, "_hook_kwargs", {}).get("error_policy") == ErrorPolicy.SKIP)

    print("== 配置默认值 ==")
    check("默认 enabled=True", inst.config.plugin.enabled is True)
    check("默认 strip_assistant_messages=True", inst.config.filter.strip_assistant_messages is True)
    check("默认 strip_reasoning_messages=False", inst.config.filter.strip_reasoning_messages is False)
    check("config_version 同步", inst.config.plugin.config_version == plugin.SUPPORTED_CONFIG_VERSION)

    print("== Hook：默认开启（assistant 过滤开，reasoning 关） ==")
    kwargs = make_planner_kwargs()
    res = await inst.hook_strip_assistant(**kwargs)
    check("action=continue", res.get("action") == "continue", str(res))
    modified = res.get("modified_kwargs", {})
    check("有 modified_kwargs", "items" in modified, str(modified.keys()))
    kept = modified.get("items", [])
    check("过滤 2 条 assistant（reasoning 默认不过滤）", len(kept) == len(kwargs["items"]) - 2, str(len(kept)))
    check("保留 system/user", any(i["item_type"] == "SystemMessageItem" for i in kept)
          and any(i["item_type"] == "UserMessageItem" for i in kept))
    check("保留 FunctionCallItem/OutputItem", any(i["item_type"] == "FunctionCallItem" for i in kept)
          and any(i["item_type"] == "FunctionCallOutputItem" for i in kept))
    check("assistant 已移除", not any(i["item_type"] == "AssistantMessageItem" for i in kept))
    check("reasoning 保留（默认关）", any(i["item_type"] == "ReasoningItem" for i in kept))
    check("其余 kwargs 原样保留", modified.get("session_id") == "sess1"
          and modified.get("selected_history_count") == 8)

    print("== Hook：开启 reasoning 过滤 ==")
    inst.config.filter.strip_reasoning_messages = True
    res1b = await inst.hook_strip_assistant(**make_planner_kwargs())
    kept1b = res1b.get("modified_kwargs", {}).get("items", [])
    check("assistant+reasoning 共过滤 3 条", len(kept1b) == len(make_planner_kwargs()["items"]) - 3, str(len(kept1b)))
    check("reasoning 已移除", not any(i["item_type"] == "ReasoningItem" for i in kept1b))
    inst.config.filter.strip_reasoning_messages = False

    print("== Hook：关闭 assistant 开关 ==")
    inst.config.filter.strip_assistant_messages = False
    res2 = await inst.hook_strip_assistant(**make_planner_kwargs())
    kept2 = res2.get("modified_kwargs", {}).get("items", [])
    check("无过滤（两个开关都关）→ 不改写", "modified_kwargs" not in res2, str(res2))
    check("assistant 消息保留", any(i["item_type"] == "AssistantMessageItem" for i in kwargs["items"]))
    inst.config.filter.strip_assistant_messages = True

    print("== Hook：无 assistant 不改写 ==")
    clean_kwargs = make_planner_kwargs(n_assistant=0, n_reasoning=0)
    res4 = await inst.hook_strip_assistant(**clean_kwargs)
    check("action=continue", res4.get("action") == "continue")
    check("无 modified_kwargs（原请求体发送）", "modified_kwargs" not in res4, str(res4))

    print("== Hook：插件禁用 ==")
    inst.config.plugin.enabled = False
    res5 = await inst.hook_strip_assistant(**make_planner_kwargs())
    check("禁用 → 不改写", "modified_kwargs" not in res5 and res5.get("action") == "continue", str(res5))
    inst.config.plugin.enabled = True

    print("== Hook：异常兜底 ==")
    res6 = await inst.hook_strip_assistant(items="not a list", session_id="sess1")
    check("items 非列表 → continue 不改写", res6.get("action") == "continue"
          and "modified_kwargs" not in res6, str(res6))

    print("== 生命周期 ==")
    await inst.on_load()
    check("on_load 正常", True)
    await inst.on_config_update(CONFIG_RELOAD_SCOPE_SELF, {}, "1.0.0")
    check("on_config_update(self) 正常", True)
    await inst.on_unload()
    check("on_unload 正常", True)

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
