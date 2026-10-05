# 更新日志

## 1.0.4（2026-09-29）

维护版（安全与规范审查整改），过滤行为不变：

- **核心函数默认值对齐**：`filter_core.strip_assistant_items` 签名默认 `strip_reasoning_messages` 由 `True` 改为 `False`，与产品配置默认值（`[filter]` 节）一致，消除直接调用时的语义漂移隐患；运行时仍由调用方按用户配置显式传入；
- **日志降级**：每次成功过滤的日志由 `INFO` 降为 `DEBUG`（活跃 bot 下几乎每次 planner 请求都命中，避免刷屏；仍只记条数，不记内容）；
- **禁用态措辞修正**：`on_load` 在插件禁用时明确提示「当前为禁用状态，不会过滤任何请求」，避免用户误以为功能在生效；
- **README 补充**：`strip_reasoning_messages` 配置说明与 FAQ 点名「要求回传 reasoning 的提供方（OpenAI Responses API 系）上开启后可能触发上游报错」；日志示例同步更新；
- manifest 内联 i18n（en 翻译随配置模型内联、不提供 locales_path）补充「刻意设计」说明注释，结构不变。

## 1.0.3

面向 MaiBot 1.3.0（+ maibot_sdk 2.8.2）的兼容性声明修正，功能与过滤行为完全不变，**仍兼容 1.2.x 宿主**：

- **版本区间修正**：`sdk.min_version` 由 `2.0.0` 修正为 `2.8.1`（代码实际依赖的 Hook / 配置模型 API 所需的最低已验证 SDK；1.2.x 宿主自带 2.8.1，不受影响）；
- **配置 WebUI 元数据补全**：每个配置字段补充 `i18n` 英文翻译（`label`/`hint`），每个配置分组补充 `__ui_i18n__`（英文标题与说明），manifest `i18n.supported_locales` 增加 `en`——英文界面下 WebUI 不再直接显示英文字段名；
- README 同步：兼容区间说明、`config_version` 示例值与版本历史表更新。

## 1.0.2

为全部配置项补充/完善了用户友好的中文注释与说明（悬停提示），完善配置节说明；插件功能与行为不变。

## 1.0.1（2026-08-28）

- **插件类型修正**：`_manifest.json` 的 `plugin_type` 由 `tool` 改为 `extension`（插件为纯 Hook 扩展，未定义 tool/command，避免 WebUI 分类误导）。
- **描述更新**：description 明确为 DeepSeek V4 flash（使用的提供方含 Command Code、阿里云百炼）。

## 1.0.0（2026-08-28）

- 首个版本。
- 功能：
  - 监听 `maisaka.planner.before_request` Hook（BLOCKING 模式），在 Planner 请求模型前过滤 `messages` / Context Items 中所有 `role=assistant` 的纯文本消息（仅保留 system、user、tool 角色），修复 DeepSeek V4 系列模型（含 Command Code、阿里云百炼）Planner 工具调用失败问题。
  - 保留 `FunctionCallItem` / `FunctionCallOutputItem`（协议原子段，删除会破坏工具调用链）。
  - 只影响本次临时请求体，不回写聊天历史，不影响其它模型。
  - 可配置开关：`strip_assistant_messages`（默认开）、`strip_reasoning_messages`（默认关）。
  - 无第三方依赖，不声明 capabilities。
