# 作业 01：让 Agent 真正操作工作区

## 交付目标

实现一个文件工具模块，让当前 TUI 中的 Agent 能完成：查看目录 → 搜索内容 → 读取文件 → 创建文件 → 精确修改 → 重新读取验证。

操作对象是真实磁盘文件；推理由项目现有 LM Studio OpenAI 兼容 API 完成，不使用模拟模型验收。工作区选择和路径检查已经提供，你负责工具实现及注册。现有天气工具返回模拟数据，不属于这次验收。

## 文件放哪里

| 内容 | 位置 |
| --- | --- |
| 你的实现 | `src/learn_smolagents/tools/filesystem.py` |
| 工具注册 | `src/learn_smolagents/agent/runtime.py` |
| 已有路径边界 | `src/learn_smolagents/workspace/context.py` |
| 你编写的自动测试 | `tests/test_file_tools.py` |
| 验收记录 | `docs/assignments/01-file-tools-results.md`（完成时创建） |

不要在根目录添加实验脚本。自动测试使用 pytest 的 `tmp_path`；真实模型操作的文件放进 TUI 新建的独立工作区。不要拿应用源码目录进行修改验收。

## 本次确定的工具接口

五个工具都返回字符串。列表、搜索、写入结果用 `json.dumps(..., ensure_ascii=False)` 编码；读取返回带行号的正文。模型需要能从结果中判断下一步操作，不要只返回“成功”。

| 工具签名 | 要求 |
| --- | --- |
| `list_directory(path: str = ".") -> str` | 只列直接子项，按名称排序。返回 JSON 数组，条目包含 `path`（工作区相对路径）、`type`（`file` 或 `directory`）。跳过符号链接。 |
| `read_file(path: str, start_line: int = 1, end_line: int = 200) -> str` | UTF-8 文本；行号从 1 开始、两端包含；格式为 `1: 正文`。要求 `1 <= start_line <= end_line`，一次最多 200 行。超过文件末尾截到末尾，起点超过末尾返回空字符串。 |
| `search_text(query: str, path: str = ".", max_results: int = 50) -> str` | 在目录下递归进行区分大小写的字面搜索。每个命中行返回一次，包含 `path`、`line`、`text`。返回对象包含 `matches` 和 `truncated`。按相对路径、行号排序。空查询拒绝；结果上限为 1–200。 |
| `create_file(path: str, content: str) -> str` | 创建 UTF-8 文件；父目录必须存在；已有文件拒绝覆盖。返回 `path` 和 `bytes_written`（UTF-8 字节数）。 |
| `edit_file(path: str, old_text: str, new_text: str) -> str` | 只允许唯一精确匹配。空旧文本、零匹配、多匹配均报错且不修改。返回 `path` 和 `replacements: 1`。保留未修改部分的换行形式。 |

共同约束：

- 每次调用内部执行 `workspace.resolve(path)`，禁止 `os.chdir()` 和自己拼接绕开边界。
- 文件读取和修改限制为 1 MiB；超过限制拒绝。创建和修改后的内容也不超过 1 MiB。
- 搜索跳过 `.git`、`.venv`、`__pycache__` 目录、符号链接、超限文件及非 UTF-8 文件；其他读取错误应明确报告。
- 搜索只有发现第 `max_results + 1` 条命中，才能确定 `truncated` 为 `true`。
- 直接读取非法路径、目录、非 UTF-8 文件等情况抛出清晰异常。不要把异常转换成看起来成功的空结果。
- 所有 `@tool` 的参数都写 Google 风格 `Args:` 描述。模型通过这些描述理解参数含义。

## 我提供的关键代码

### 1. 工厂和装饰器如何接起来

`@tool` 会把函数变成 smolagents 的工具对象。内层函数闭包持有 `workspace`，所以调用时能拿到当前选择。

下面是结构示例，工具主体由你填写。最终工厂返回五个工具，示例只展示一个：

```python
from smolagents import Tool, tool
from learn_smolagents.workspace import WorkspaceContext


def build_file_tools(workspace: WorkspaceContext) -> list[Tool]:
    @tool
    def read_file(path: str, start_line: int = 1, end_line: int = 200) -> str:
        """Read a UTF-8 workspace file with inclusive, one-based line numbers.

        Args:
            path: File path relative to the selected workspace.
            start_line: First line to include, starting at one.
            end_line: Last line to include; at most 200 lines per call.
        """
        target = workspace.resolve(path)
        # 你完成：参数检查、大小限制、读取、行号和截取。
        raise NotImplementedError

    return [read_file]
```

注意：`resolve` 负责路径边界，不负责文件类型、大小、编码和业务约束。这些检查由你的工具负责。

### 2. 创建时保证已有文件不被覆盖

不要使用“先判断不存在，再用 w 模式写入”。下面的 `x` 模式由文件系统拒绝已有目标：

```python
with target.open("x", encoding="utf-8", newline="") as stream:
    stream.write(content)
```

先检查内容字节数，再打开文件。`newline=""` 避免文本写入时转换换行符。

### 3. 精确编辑的核心判断

```python
if not old_text:
    raise ValueError("old_text 不能为空")

with target.open("r", encoding="utf-8", newline="") as stream:
    original = stream.read()

count = original.count(old_text)
if count != 1:
    raise ValueError(f"需要唯一匹配，实际匹配 {count} 次；请提供更完整的上下文")

updated = original.replace(old_text, new_text, 1)
```

你完成：读取前的大小检查、更新后的字节上限、写回和结果。所有校验通过以后才能以写入模式打开目标文件；测试必须证明校验失败时原文件不变。

### 4. 注册位置

完成五个工具以后，在 `agent/runtime.py` 导入工厂，并把 `_create_agent()` 中的工具列表改成：

```python
tools=[get_temperatuer, get_mac_info, *build_file_tools(self.workspace)],
```

目前骨架会抛出 `NotImplementedError`，所以尚未注册；现有 TUI 可以正常使用。不要在完成之前注册空壳。

## 实现顺序

1. `list_directory` 和 `read_file`：先让 Agent 看懂目录及文本。
2. `create_file`：验证独占创建，补上写入结果。
3. `edit_file`：确保失败时文件不变，再验证成功修改。
4. `search_text`：递归扫描、跳过规则、稳定排序和截断。
5. 工厂注册、自动测试、真实模型全流程。

## 自动验收：由你写测试

通过工厂返回的对象调用工具，而不只是测试私有辅助函数：

```python
tools = {item.name: item for item in build_file_tools(WorkspaceContext(tmp_path))}
result = tools["read_file"](path="README.md", start_line=1, end_line=10)
```

你需要覆盖这些结果：

- 五个工具名精确匹配接口表，工厂能被导入，参数描述可以生成 schema。
- 中文文本读写、空文件、行范围、大小上限和 UTF-8 字节计数。
- 创建遇到已有文件时拒绝，旧内容保持不变。
- 编辑零匹配、多匹配、空旧文本时拒绝；唯一匹配成功；CRLF 文件未编辑部分的换行保持不变。
- 搜索顺序稳定；二进制、忽略目录和符号链接不会进入结果；恰好到达上限与真正超限的 `truncated` 不同。
- 绝对路径、`../` 越界、指向外部的符号链接均不能用于读写。
- 修改同一个 `WorkspaceContext.root` 后，用已创建的工具再次调用，访问的是新工作区。

运行：

```sh
uv run python -m pytest tests/test_file_tools.py -q
env -u NO_COLOR uv run python -m pytest -q
```

不要把未执行的真实模型步骤写成通过。单元测试通过和模型正确使用工具是两件事。

## 真实 API 验收

模型连接通过 TUI 标题栏的「LLM 配置」设置，配置按环境保存在本机。启动命令为 `sh scripts/environment.sh development`。真实 API 连通性需独立验收。

在 TUI 新建一个专用工作区，按顺序发送：

1. “查看当前目录，然后创建 README.md，内容为两行：第一行 # Notes Service，第二行 status: draft。读取文件确认。”
2. “搜索 status: draft，把它精确改为 status: ready，重新读取确认。”
3. “再次创建 README.md，内容为 overwritten；如果文件已存在，应报告失败并保留原内容。”
4. “把 README.md 中的 status: missing 改为 status: done；找不到时说明原因，保持原文件。”
5. 切到另一个空工作区：“列出目录，检查这里是否存在 README.md。”结果不得沿用上一个工作区的文件。

验收记录写下：测试命令和实际结果、模型操作后的磁盘内容、一次失败及你怎么定位它。模型口头说完成不足以验收，必须检查文件。

## 交回来时

告诉我“文件工具作业完成，检查”，我会检查工具契约、失败时是否误写、工作区切换及模型调用链。重点是你能解释：为什么路径在调用时解析、为什么创建用 x、为什么多匹配编辑必须拒绝。
