# 不要只说不干（MaiBot 插件）

在 **Planner** 构造发送给 LLM 的请求体之前，自动过滤掉 `messages` 数组中所有 **`role` 为 `assistant`** 的消息（仅保留 `system`、`user`、`tool` 角色的消息），修复 DeepSeek V4 系列模型（Command Code、阿里云百炼）**工具调用失败**的问题。

> 相关讨论见 [MaiBot issue #2017](https://github.com/Mai-with-u/MaiBot/issues/2017)。

> 如果你发现 planner 决策声明回复而没有任何 reply 的调用，可以尝试使用该插件解决。

## 功能

- **Planner 请求前过滤**：监听 `maisaka.planner.before_request` Hook（BLOCKING 模式），在规划器向模型发起请求前改写 `kwargs["items"]`，移除所有纯文本 assistant 消息（`AssistantMessageItem`）与推理内容（`ReasoningItem`），仅保留 `system` / `user` / `tool` 角色；
- **不破坏工具协议**：保留 `FunctionCallItem`（assistant 工具调用）与 `FunctionCallOutputItem`（tool 结果）——二者是协议原子段，删除调用段会使结果段变成「孤儿 function output」，MaiBot 会整体拒绝该改写；
- **只影响临时请求体**：仅改写本次发往 LLM 的请求，**不回写聊天历史**，不影响其它模型（GPT-4、Claude 等对 Assistant 消息兼容性更好的模型不受影响）；
- **可配置开关**：默认开启，可按需关闭（见下文配置）；
- **无第三方依赖**：纯 SDK 插件，不声明任何 `capabilities`（无需额外能力），不影响任何能力代理。

## 安装

1. 将插件目录（含 `_manifest.json`、`plugin.py` 等）放入 MaiBot 的 `plugins/` 目录。
2. 重启 MaiBot，或在 WebUI 插件中心安装。
3. 插件为标准 SDK 插件（`maibot-plugin-sdk`，由 MaiBot Runner 内置提供），**无第三方依赖**，无需手动安装任何包。

> 兼容：`host_application` `1.0.0 ~ 1.99.99`，`sdk` `2.0.0 ~ 2.99.99`（Manifest v2）。

## 配置

插件加载后由 Runner 在插件目录生成 `config.toml`，可在 WebUI 修改：

```toml
[plugin]                     # 插件总开关与版本号（独立一项分类）
enabled = true               # 是否启用插件（关闭后不过滤任何请求）
config_version = "1.0.1"     # 配置版本（与插件版本同步，UI 中隐藏）

[filter]                     # 过滤设置
strip_assistant_messages = true   # 过滤纯文本 assistant 消息（默认开）
strip_reasoning_messages = false  # 同时过滤推理内容 ReasoningItem（默认关）
```

### 配置项一览

| 配置项 | 说明 |
|--------|------|
| `plugin.enabled` | 是否启用插件（默认开）。关闭后不过滤任何请求 |
| `plugin.config_version` | 配置版本（与插件版本同步，UI 中隐藏） |
| `filter.strip_assistant_messages` | 是否过滤纯文本 assistant 消息（默认开）。这些消息可能包含「决策：保持安静，不回复、不调用工具」等负面示范，会干扰 DeepSeek V4 系列模型的工具调用判断 |
| `filter.strip_reasoning_messages` | 是否同时过滤推理内容 `ReasoningItem`（assistant 思考文本，默认关） |

> 如果使用对 Assistant 消息兼容性较好的模型（如 GPT-4、Claude）且不希望过滤上下文，可在 WebUI 关闭 `strip_assistant_messages`（`strip_reasoning_messages` 默认已关闭）。

## 工作原理

MaiBot 的 Planner 在向 LLM 发送请求时，会把历史对话中的 `AssistantMessageItem`（含模型之前输出的纯文本分析）作为上下文一并提交。对 DeepSeek V4 系列模型，这些含「不调用工具」决策的纯文本分析会污染模型的输出分布（「坏示例」污染）。

本插件在 `maisaka.planner.before_request`（规划器请求模型前、允许改参的 Hook 点）改写请求载荷：

```
Planner 构造请求体（items: Context Item 快照列表）
 → maisaka.planner.before_request Hook（本插件，BLOCKING）
     → 移除 item_type == "AssistantMessageItem"（纯文本 assistant）
     → 移除 item_type == "ReasoningItem"（推理内容，默认关闭）
     → 保留 SystemMessageItem / UserMessageItem / FunctionCallItem / FunctionCallOutputItem
 → 反序列化后的请求体发送给 LLM
```

- **返回**：移除条数 > 0 时返回 `{"action": "continue", "modified_kwargs": {"items": [...]}}`；
- **未过滤**：返回 `{"action": "continue"}`（不触发改写，原请求体原样发送）；
- **异常**：`error_policy=SKIP`，记录日志并继续原请求（不会误伤正常请求）。

## 日志示例

```
[INFO] 不要只说不干：已加载（过滤 assistant 纯文本=True，过滤推理内容=False）
[INFO] 已过滤 8 条 assistant 消息（保留 system/user/tool，仅本次请求，不回写历史）
[INFO] 不要只说不干：配置已更新（过滤 assistant 纯文本=False，过滤推理内容=False）
```

## 常见问题

- **planner 决策声明回复但没有任何 reply 调用？** 这通常是上下文中残留的纯文本 assistant 分析（如「决策：保持安静，不回复、不调用工具」）污染了模型判断。安装本插件（默认配置即可）即可在请求前滤除这些消息，提高工具调用成功率。
- **为什么我的模型不是 DeepSeek V4 也用不上？** 本插件默认开启过滤。若你的模型（如 GPT-4、Claude）依赖 Assistant 消息上下文，可在 WebUI 关闭 `filter.strip_assistant_messages`（`strip_reasoning_messages` 默认已关闭），插件即不再改写任何请求。
- **过滤会不会影响回复质量？** 只影响「纯文本 assistant 分析」与「推理内容」，不影响用户消息、系统提示、工具调用与工具结果。工具调用段的保留保证 tool 结果仍能被模型正确看到。
- **会不会回写聊天历史？** 不会。仅改写本次临时 LLM 请求体，聊天历史保持原样。

## 版本历史

| 版本 | 变更 |
|------|------|
| 1.0.1 | `plugin_type` 改为 `extension`；description 明确为 DeepSeek V4 flash；新增 `test/` 单元测试 |
| 1.0.0 | 初始版本：`maisaka.planner.before_request` Hook 过滤 assistant 纯文本消息与推理内容；配置开关 `strip_assistant_messages` / `strip_reasoning_messages` |

## 文件结构

```
cateye_filter_assistant/
├── _manifest.json      # 插件清单（Manifest v2）
├── plugin.py           # SDK 插件入口（配置模型、Hook 过滤；依赖 maibot_sdk）
├── filter_core.py      # 核心逻辑（角色识别、过滤规则；纯 Python，不依赖 SDK）
├── __init__.py
├── README.md
└── LICENSE             # MIT
```

## 开发与测试

本插件为标准 **MaiBot SDK 插件**（基于 `maibot-plugin-sdk`）。

- **`filter_core.py`**：核心逻辑（Item 角色识别、过滤规则）**不依赖 SDK**，可离线单元测试；
- **`plugin.py`**：SDK 插件入口，依赖 `maibot_sdk`（由 MaiBot Runner 提供），本地开发需先安装 SDK 才能导入。

```bash
pip install maibot-plugin-sdk   # 本地开发依赖

python test/test_filter_assistant_core.py    # 核心逻辑单元测试（不依赖 SDK）
python test/test_filter_assistant_plugin.py  # 插件类集成测试（stub SDK，无需真实 SDK 环境）
```
