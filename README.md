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
