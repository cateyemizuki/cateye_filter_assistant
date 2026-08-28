# 更新日志

## 1.0.1（2026-08-28）

- **插件类型修正**：`_manifest.json` 的 `plugin_type` 由 `tool` 改为 `extension`（插件为纯 Hook 扩展，未定义 tool/command，避免 WebUI 分类误导）。
- **描述更新**：description 明确为 DeepSeek V4 flash（测试时使用的提供方含 Command Code、阿里云百炼）。
- **补充测试**：新增 `test/test_filter_assistant_core.py`（核心逻辑单元测试）与 `test/test_filter_assistant_plugin.py`（插件集成测试，stub SDK），与 README「开发与测试」引用一致。

## 1.0.0（2026-08-28）

- 首个版本。
- 功能：
  - 监听 `maisaka.planner.before_request` Hook（BLOCKING 模式），在 Planner 请求模型前过滤 `messages` / Context Items 中所有 `role=assistant` 的纯文本消息（仅保留 system、user、tool 角色），修复 DeepSeek V4 系列模型（含 Command Code、阿里云百炼）Planner 工具调用失败问题。
  - 保留 `FunctionCallItem` / `FunctionCallOutputItem`（协议原子段，删除会破坏工具调用链）。
  - 只影响本次临时请求体，不回写聊天历史，不影响其它模型。
  - 可配置开关：`strip_assistant_messages`（默认开）、`strip_reasoning_messages`（默认关）。
  - 无第三方依赖，不声明 capabilities。
