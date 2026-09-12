# 开发规范实施计划

- [x] 新增配置模块：按 development、test、production 隔离 LLM 与工作区配置。
- [x] TUI 提供模型名称、API 地址和密钥编辑、保存；保存后重建 Agent。
- [x] 将现有本地密钥迁入忽略的本地配置，移除源码中的密钥。
- [x] 保留现有 UI、工具和工作区模块边界，模型配置从 Agent 中解耦。
- [x] 配置独立测试环境，补齐忽略规则与使用说明。
- [x] 验证配置持久化、环境隔离、TUI 保存及现有测试。

验证结果：独立测试环境 32 项测试通过；新增配置模块与 Agent 的 Ruff 检查通过；shell 语法及本地文件忽略规则通过。未调用真实模型 API。

## 目录模块化修正

- [x] Agent 运行逻辑迁入 `agent/runtime.py`。
- [x] 工作区上下文与存储拆为 `workspace/context.py`、`workspace/store.py`。
- [x] 权限策略和访问协调迁入 `permissions/`，启动入口迁入 `cli/`。
- [x] 同步全部导入和文档，保持原有程序目录删除保护范围。
- [x] 验证测试、安装后的命令入口和模块入口。

目录模块化修正验证：33 项测试通过；生产安装包重新构建后，子包导入、命令行入口及模块入口调用均通过（模拟 TUI run）。

## 2026-09-11 异常行为修复

优先使用 smolagents 原生 CodeAgent instructions、ToolCall、AgentParsingError、RunResult、TokenUsage 和 Timing，不复制执行循环。

- [x] 原生提示与协议约束，删除模板静默回退。
- [x] 类型化错误处理、解析恢复记录与最终状态。
- [x] 递归概览/完整清点范围、深度边界与既有递归删除。
- [x] 工具标签遵循原生 ToolCall。
- [x] 本轮 token 和步骤耗时语义。
- [x] 权限文案与现有策略一致。
- [x] 保留符号链接身份和路径，不递归跟随。
- [x] 区分 UI 截断与原生观察输出限制。
- [x] 临时目录、真实解释器、受控模型及 TUI 回归验证。

修改前直接运行测试：92 passed、2 个背景色断言失败。随后按项目脚本清除 NO_COLOR，两个背景断言均通过；未修改背景色。

完成验证：

- `env -u NO_COLOR .venv-test/bin/python -m pytest -q`：106 passed。
- 本次修改的运行逻辑、文件工具、UI、渲染器及相关测试：Ruff 检查与格式检查通过。
- `basedpyright src/learn_smolagents/agent/runtime.py src/learn_smolagents/tools/filesystem.py --level error`：0 errors。
- 扩大到 UI 的类型检查仍报告原有 `app.py → router.py → app.py` 类型引用环（router 的回引位于 TYPE_CHECKING，已核对 HEAD）；非本轮引入，未改路由架构。
- 宽屏 132×39、窄屏 48×26 的 TUI 渲染已检查；修复权限标签裁切，截图与临时配置已清理。
- 全量 `git diff --check` 仍报告用户原有 conversation.py、theme/__init__.py 文件末尾空行；这两个文件未在本轮改动。

原生 CodeAgent + ScriptedModel 回归覆盖：受限导入失败及恢复、纯文本协议失败及恢复、步数耗尽的失败状态和兜底 token、连续两轮保留记忆但隔离统计、规划 token、用量缺失、原生日志截断、递归工具执行及符号链接目标保护。UI 按原生步骤编号去重，保留简洁恢复记录和完整观察记录，显示本轮状态与统计。

未调用外部模型 API；重复探索和协议遵循属于模型行为，本轮验证原生恢复机制与工具替代路径，不宣称任意模型永不重试。

## 2026-09-12 验收遗漏补修

- [x] 仅隐藏可静态确认的字面量 final_answer；保留间接调用、嵌套调用和计算步骤。
- [x] 失败步骤先记录已有原生观察，再记录错误，不重复 ToolOutput。
- [x] 目录渲染以查询/工作区为根，按相对路径建立层级，保留链接和省略信息。
- [x] 以验收复现案例新增真实解释器/TUI 回归，并完成全量测试。

补修验证：

- 新增 14 项回归覆盖列表/字典间接删除、函数别名、非字面量回答、部分成功日志、ToolOutput 去重、相对/绝对路径、同名文件、子目录根、链接及显示限制。实际删除仅发生在 pytest 临时目录。
- `env -u NO_COLOR .venv-test/bin/python -m pytest -q`：120 passed（16.46s）。
- 本次修改的 app.py、renderers.py 及两个测试文件 Ruff 和格式检查通过；本次跟踪文件的 diff 空白检查通过。
- renderers.py 的 basedpyright 错误级检查通过。连同 app.py 检查时仍有此前披露的 TYPE_CHECKING 引用环；无新增类型诊断。
- 用真实目录工具的输出复核 132×39 和 48×32 TUI：src/a.py 与 tests/a.py 位于各自分支，符号链接身份保留，出错前日志位于错误之前。临时目录、截图和配置已清理。
- README 已同步：仅省略直接字面量 final_answer，非字面量表达式保留执行卡片；失败步骤保留已有观察。

本节补齐此前独立验收的三项遗漏；未调用外部模型 API。

> 恢复说明：本节与上一节在 2026-09-12 10:08 被误操作回退，于同日按备份写回。
