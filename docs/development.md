# 开发与环境管理

## 日常命令

在项目根目录运行：

```sh
# 开发：安装锁定依赖并启动 TUI
sh scripts/environment.sh development

# 测试：独立依赖环境，执行自动测试
sh scripts/environment.sh test

# 稳定运行：不安装开发依赖，以非 editable 方式安装项目
sh scripts/environment.sh production
```

每条命令都可以在末尾加 `setup`，只安装环境、不启动程序。

| 环境 | Python 环境 | 配置目录 |
| --- | --- | --- |
| development（默认） | `.venv/` | `~/.config/learn-smolagents/development/` |
| test | `.venv-test/` | `~/.config/learn-smolagents/test/` |
| production | `.venv-production/` | `~/.config/learn-smolagents/production/` |

配置目录内分别保存 `llm.json` 和 `workspaces.json`。自动测试会将配置根目录覆盖为每个测试自己的临时目录，不读写用户配置、不请求真实模型。

`LEARN_SMOLAGENTS_ENV` 选择上述三个环境；`LEARN_SMOLAGENTS_CONFIG_DIR` 可指定配置根目录，实际使用其下对应环境的子目录。旧版根目录下的 `workspaces.json` 不会被删除；需要恢复时，在程序关闭后将其复制到所需环境目录。

环境隔离依赖和配置，不是文件访问沙箱。开发时在 TUI 选择专门的练习目录，生产环境选择实际工作目录。正式使用稳定版本时，在独立 Git checkout 中固定到验收过的版本，再执行 production 命令；在开发目录执行此命令会安装当前源码。

## LLM 配置

点击标题栏的「LLM 配置」，填写模型名称、完整 API 地址和密钥，然后保存。密钥输入框隐藏字符；配置以仅当前用户可读写的本地 JSON 文件保存。保存后重建 Agent 并开始新会话，保留输入草稿。请求执行期间不能修改配置。

每个环境独立配置。新环境没有预设密钥，需要先通过 TUI 保存配置。代码只读取配置，不再内置模型名称、API 地址或密钥。

## 模块职责

- `cli/entrypoint.py`：命令行启动；包根目录只保留 Python 包标记和模块启动入口。
- `config/`：环境路径、LLM 配置校验与本地持久化。
- `agent/runtime.py`：根据传入配置创建模型、注册工具、管理 Agent 会话。
- `ui/settings.py`：LLM 设置弹窗。
- `ui/app.py`：主界面、会话交互与模块连接。
- `ui/workspaces.py`、`workspace/context.py`、`workspace/store.py`：工作区界面与工作区数据管理。
- `permissions/access.py`、`permissions/policy.py`、`ui/approval.py`：文件访问授权。
- `tools/`：文件工具。
- `scripts/`：环境安装与运行入口。
- `tests/`：隔离配置和文件数据的自动测试。

## Git 管理

提交源码、测试、文档、脚本、`.python-version`、`pyproject.toml` 和 `uv.lock`。不提交密钥、虚拟环境、本机配置、缓存、覆盖率输出或工作数据。项目内的本地文件统一放入 `.local/`；`.env` 及其环境变体也已忽略，但应用不会自动读取 `.env`。

每次围绕一个功能修改，运行测试后提交。模型真实调用还需要在开发环境手动验收；测试通过不代表远程模型连接已验证。
