"""不要只说不干 — MaiBot 插件入口。

在 Planner 构造发送给 LLM 的请求体之前，自动过滤掉 messages / Context Items 中
所有 role 为 assistant 的纯文本消息（仅保留 system、user、tool 角色），
修复 DeepSeek V4 系列模型（Command Code、阿里云百炼）因上下文中的
「决策：保持安静，不回复、不调用工具」等负面示范导致工具调用失败的问题。

实现：
- 通过 ``maisaka.planner.before_request`` Hook（BLOCKING 模式）改写
  ``kwargs["items"]``：该 Hook 在 Maisaka 规划器请求模型前触发，
  ``items`` 为即将发送给模型的 Context Item 快照（不含 replay payload），
  允许改参（``allow_kwargs_mutation=True``），改写结果会被反序列化并用于实际请求；
- 过滤规则见 ``filter_core.strip_assistant_items``：
  移除纯文本 assistant 消息（AssistantMessageItem）与推理内容（ReasoningItem），
  保留 system / user / tool 消息与工具调用段（FunctionCallItem + FunctionCallOutputItem
  是协议原子段，删除会导致 tool 结果变孤儿而被整体拒绝）；
- 只影响本次临时请求体，**不回写聊天历史**，不影响其它模型。

配置：
- ``[plugin]`` 节：``enabled``（插件总开关）与 ``config_version``（配置版本，与插件版本同步）；
- ``[filter]`` 节：``strip_assistant_messages``（过滤纯文本 assistant 消息，默认开启）、
  ``strip_reasoning_messages``（过滤推理内容 ReasoningItem，默认关闭）。
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Iterable

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder

from .filter_core import strip_assistant_items

# 配置版本（config_version）：与 _manifest.json 的 version 保持同步。
# config_version 用于检查配置文件（config.toml）是否需要更新。
SUPPORTED_CONFIG_VERSION = "1.0.2"

# 对应 maiBot Context Item 载荷的 schema 版本键（与 Host 传入一致，回传时保留原值）
# 该值来自 src/llm_models/payload_content/context_item.py 的 CONTEXT_ITEM_SCHEMA_VERSION，
# 插件不写死具体数字，仅在回传时沿用 Host 传入值。


class PluginSectionConfig(PluginConfigBase):
    """插件自身配置（plugin 配置节）：总开关与配置版本。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(
        default=True,
        description="是否启用插件（关闭后不过滤任何请求）",
        json_schema_extra={
            "label": "启用插件",
            "hint": "插件总开关",
        },
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="配置版本（与插件版本同步，用于检查配置文件是否需要更新）",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "label": "配置版本",
            "hint": "配置版本，勿改",
        },
    )


class FilterSectionConfig(PluginConfigBase):
    """过滤设置（filter 配置节）：需要过滤哪些内容。"""

    __ui_label__ = "过滤设置"
    __ui_icon__ = "filter_alt"
    __ui_order__ = 1

    strip_assistant_messages: bool = Field(
        default=True,
        description="过滤纯文本 assistant 消息（含「不调用工具」坏示例；仅影响临时请求体，不回写历史）",
        json_schema_extra={
            "label": "过滤 assistant 纯文本消息",
            "hint": "过滤助手纯文本消息",
        },
    )
    strip_reasoning_messages: bool = Field(
        default=False,
        description="同时过滤推理内容（ReasoningItem，assistant 思考文本；默认关闭）",
        json_schema_extra={
            "label": "过滤推理内容",
            "hint": "也过滤推理内容",
        },
    )


class CateyeFilterAssistantConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    filter: FilterSectionConfig = Field(default_factory=FilterSectionConfig)


class CateyeFilterAssistantPlugin(MaiBotPlugin):
    """不要只说不干：Planner 请求前过滤 assistant 纯文本消息，修复工具调用失败。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = CateyeFilterAssistantConfig
    config_reload_subscriptions: ClassVar[Iterable[str]] = ()

    @HookHandler(
        "maisaka.planner.before_request",
        name="strip_assistant_messages",
        description="Planner 请求模型前过滤 role=assistant 的纯文本消息（仅保留 system/user/tool）",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def hook_strip_assistant(self, **kwargs: Any) -> Dict[str, Any]:
        """改写 planner 请求体：移除 assistant 纯文本消息与推理内容。"""
        try:
            if not self.config.plugin.enabled:
                return {"action": "continue"}

            items = kwargs.get("items")
            if not isinstance(items, list):
                return {"action": "continue"}

            result = strip_assistant_items(
                items,
                strip_assistant_messages=bool(self.config.filter.strip_assistant_messages),
                strip_reasoning_messages=bool(self.config.filter.strip_reasoning_messages),
            )
            if result["removed"] <= 0:
                return {"action": "continue"}

            modified = dict(kwargs)
            modified["items"] = result["items"]
            self.ctx.logger.info(
                "已过滤 %d 条 assistant 消息（保留 system/user/tool，仅本次请求，不回写历史）",
                result["removed"],
            )
            return {"action": "continue", "modified_kwargs": modified}
        except Exception as e:
            # error_policy=SKIP 已兜底，这里再记录日志便于排查
            self.ctx.logger.warning("过滤 assistant 消息异常（本次不过滤，继续原请求）：%s", e)
            return {"action": "continue"}

    def _check_config_version(self) -> None:
        """检测配置版本并自动兼容旧版配置文件（缺失字段由 Runner 按默认值补齐）。"""
        try:
            raw = self.get_plugin_config_data()
            current = str((raw.get("plugin") or {}).get("config_version") or "").strip()
        except Exception:
            return
        if current and current != SUPPORTED_CONFIG_VERSION:
            self.ctx.logger.info(
                "检测到旧版配置（config_version=%s，当前支持 %s），缺失字段已按默认值自动补齐",
                current,
                SUPPORTED_CONFIG_VERSION,
            )

    async def on_load(self) -> None:
        self._check_config_version()
        self.ctx.logger.info(
            "不要只说不干：已加载（过滤 assistant 纯文本=%s，过滤推理内容=%s）",
            bool(self.config.filter.strip_assistant_messages),
            bool(self.config.filter.strip_reasoning_messages),
        )

    async def on_unload(self) -> None:
        self.ctx.logger.info("不要只说不干：已卸载")

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        del config_data, version
        if scope != CONFIG_RELOAD_SCOPE_SELF:
            return
        self._check_config_version()
        self.ctx.logger.info(
            "不要只说不干：配置已更新（过滤 assistant 纯文本=%s，过滤推理内容=%s）",
            bool(self.config.filter.strip_assistant_messages),
            bool(self.config.filter.strip_reasoning_messages),
        )


def create_plugin() -> CateyeFilterAssistantPlugin:
    return CateyeFilterAssistantPlugin()
