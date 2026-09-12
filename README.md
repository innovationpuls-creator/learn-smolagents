# Local CodeAgent

开发启动：`sh scripts/environment.sh development`。点击标题栏「LLM 配置」管理模型与密钥。详见[开发与环境管理](docs/development.md)。

也可以使用 `uv run local-codeagent`。也支持 `uv run python -m learn_smolagents` 和原来的 `uv run python main.py`。

## 工作区管理

点击标题栏的「工作区 Ctrl+W」或按 `Ctrl+W`：

- 输入绝对路径或 `~/...`，点「创建目录」创建并切换到新目录。已有目录不会被覆盖。
- 输入已有目录，或从列表选择目录，点「打开 / 切换」。这会更换工作区，不搬迁原目录文件。
- 删除时从列表选择目标，在确认框输入它的完整路径，然后点「删除工作区」。**目录及全部文件会被删除**。程序目录、启动目录、主目录、配置目录及它们的上级受到保护。
- 正在处理请求时不能切换或删除。切换到其他工作区后重建 Agent、清空旧对话，保留未发送草稿。
- 删除当前工作区后，需要重新选择工作区才能发送消息。

目录列表与当前选择保存于 `~/.config/learn-smolagents/<环境>/workspaces.json`（默认环境为 `development`）。首次打开时使用启动目录；后续恢复已保存的选择。

## 项目结构

```text
src/learn_smolagents/
  config/                # 环境与 LLM 配置
  cli/entrypoint.py      # 启动入口
  agent/runtime.py       # 模型调用与 Agent 会话
  workspace/             # context.py 路径上下文；store.py 持久化
  permissions/           # policy.py 权限策略；access.py 访问协调
  ui/                    # TUI 与工作区管理面板
  tools/                 # Agent 文件工具
  assets/                # SVG 等应用资源
tests/                   # 自动测试
docs/assignments/        # 作业说明与完成记录
main.py                  # 保留原启动方式的薄入口
```

## 当前作业

[作业 01：让 Agent 真正操作工作区](docs/assignments/01-file-tools.md)。实现五个文件工具并接入现有模型 API；文档包含接口、关键代码和验收流程。

`src/learn_smolagents/tools/filesystem.py` 中的文件工具由 Agent 注册，文件访问经授权模块处理。

## 验证

`sh scripts/environment.sh test`

测试使用临时目录，覆盖创建、切换、持久化、确认后删除、路径边界、宽窄屏管理面板，以及现有对话流程。

## 执行与观察语义

- Agent 使用 smolagents 原生代码协议、受限解释器与 `final_answer`；自定义规则通过 `CodeAgent.instructions` 注入。模板加载失败会报告，不静默降级。解析错误保留恢复记录，达到步数上限的总结标记为未正常完成。
- `python_interpreter` 卡片表示整段 Python 执行，其中可能包含多个文件工具调用；不以第一个函数名代替整段动作。仅省略直接传入字面量的 `final_answer` 执行卡片；间接调用、变量和计算表达式保留执行记录。
- 每轮 token 只统计该轮 ActionStep、PlanningStep 和步数上限兜底生成；缺失用量时不显示估算数。步骤耗时包含生成与执行，不是单个文件工具耗时。
- 权限模式为工作区内允许、工作区外审批，包含文件删除；完全访问模式不询问。
- `list_directory(recursive=True)` 默认是项目概览；`skipped` 报告略过目录，`depth_limited` 报告未展开目录。完整清点使用 `include_ignored=True` 并按需继续查询深层目录。非递归列出全部直接子项。目录树以查询目录或工作区为根，按路径层级区分不同目录中的同名文件。
- 目录条目保留符号链接自身路径和类型，不跟随链接递归。单独删除链接会被拒绝；递归删除父目录只移除其中链接，不删除外部目标。
- 界面省略不改变模型观察；内存会话记录保留收到的完整原生观察；步骤失败时先记录已有输出，再记录错误，已通过 ToolOutput 显示的输出不重复。模型侧日志和执行返回值采用 smolagents 自带输出限制，已被原生截断的内容无法从会话记录恢复。
