"""Codex-level structured renderers for local CodeAgent TUI.

Provides rich visual representations for:
- Tool call execution code / arguments with syntax highlighting & panel cards
- Directory listing inspection with hierarchical/iconic Tree & summary badges
- File reading with syntax highlighting and line numbers
- Search file results with file grouping and matched line highlights
- Edit file diffs with unified diff highlighting and stats
- JSON/Dict structured data tables and pretty-printed syntax
- Plan, thought, and error cards with status badges
"""

from __future__ import annotations

import ast
import difflib
import json
import re
from os.path import commonpath
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from learn_smolagents.ui.theme.styles import CODE_THEME
from learn_smolagents.ui.theme.tokens import (
    ACCENT_ROSE,
    ACCENT_WARM,
    BG_BORDER,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FG_FAINT,
    FG_MUTED,
    FG_PRIMARY,
)

EXT_TO_LEXER: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "fish",
    ".sql": "sql",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".diff": "diff",
    ".patch": "diff",
}

FILENAME_TO_LEXER: dict[str, str] = {
    "dockerfile": "docker",
    "containerfile": "docker",
    "makefile": "makefile",
    "gnumakefile": "makefile",
    ".gitignore": "gitignore",
    ".env": "bash",
    "mvnw": "bash",
    "gradlew": "bash",
}

KNOWN_EXTENSIONLESS_FILES: set[str] = {
    "dockerfile",
    "containerfile",
    "makefile",
    "gnumakefile",
    "license",
    "licence",
    "readme",
    "procfile",
    "gemfile",
    "vagrantfile",
    "jenkinsfile",
    "mvnw",
    "gradlew",
}


def get_file_icon_and_style(filename: str) -> tuple[str, str]:
    """Return icon and style token based on filename and extension."""
    lower = filename.lower()
    base_name = Path(lower).name

    # Specific known filenames
    if base_name in ("dockerfile", "containerfile"):
        return "🐳", COLOR_INFO
    if base_name in ("makefile", "gnumakefile"):
        return "🛠 ", ACCENT_WARM
    if base_name.startswith(("license", "licence")):
        return "⚖ ", FG_MUTED
    if base_name.startswith("readme"):
        return "📝", FG_PRIMARY
    if base_name in ("mvnw", "mvnw.cmd", "gradlew"):
        return "⚡", ACCENT_WARM

    # Extension-based mapping
    if lower.endswith((".py", ".pyi")):
        return "🐍", COLOR_SUCCESS
    if lower.endswith((".html", ".htm")):
        return "🌐", COLOR_INFO
    if lower.endswith((".css", ".scss", ".sass", ".less")):
        return "🎨", ACCENT_ROSE
    if lower.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        return "🌐", COLOR_INFO
    if lower.endswith((".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg")):
        return "⚙ ", COLOR_WARNING
    if lower.endswith((".java", ".kt", ".kts")):
        return "☕", COLOR_WARNING
    if lower.endswith(".rs"):
        return "🦀", ACCENT_WARM
    if lower.endswith(".go"):
        return "🐹", COLOR_INFO
    if lower.endswith((".c", ".h", ".cpp", ".hpp")):
        return "⚙ ", COLOR_INFO
    if lower.endswith((".md", ".markdown", ".rst", ".txt")):
        return "📝", FG_PRIMARY
    if lower.endswith((".sh", ".bash", ".zsh", ".fish")):
        return "⚡", ACCENT_WARM
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp")):
        return "🖼 ", ACCENT_ROSE
    if lower.endswith((".zip", ".tar", ".gz", ".7z", ".bz2", ".xz")):
        return "📦", FG_MUTED
    if lower.endswith((".sql", ".db", ".sqlite")):
        return "💾", COLOR_INFO
    if lower.endswith((".lock", ".sum")):
        return "🔒", FG_MUTED
    if lower.startswith("."):
        return "📄", FG_MUTED
    return "📄", FG_PRIMARY


def extract_tool_arguments(tool_name: str, code_or_args: str) -> dict[str, Any]:
    """Extract known tool arguments from Python AST call or JSON dictionary, including variables."""
    result: dict[str, Any] = {}
    cleaned = code_or_args.strip()
    if not cleaned:
        return result

    # 1. Try parsing as JSON or dict literal directly
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            val = json.loads(cleaned)
            if isinstance(val, dict):
                result = dict(val)
        except (ValueError, SyntaxError, TypeError):
            pass
        if not result:
            try:
                val = ast.literal_eval(cleaned)
                if isinstance(val, dict):
                    result = dict(val)
            except (ValueError, SyntaxError, TypeError):
                pass

    if not result:
        param_orders: dict[str, list[str]] = {
            "read_file": ["file_path"],
            "list_directory": ["directory_path", "recursive", "max_depth"],
            "create_file": ["file_path", "content"],
            "edit_file": ["file_path", "old_content", "new_content"],
            "search_file": ["search_string", "directory_path"],
            "delete_file": ["file_path"],
            "delete_directory": ["directory_path", "recursive"],
        }
        expected_params = param_orders.get(tool_name, [])

        try:
            tree = ast.parse(cleaned)
        except SyntaxError:
            return result

        # Track simple variable assignments in the snippet
        symbols: dict[str, Any] = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        try:
                            val = ast.literal_eval(stmt.value)
                            symbols[target.id] = val
                        except (ValueError, SyntaxError, TypeError):
                            pass

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = ""
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr

                if call_name == tool_name or (not call_name and tool_name):
                    for idx, arg in enumerate(node.args):
                        if idx < len(expected_params):
                            if isinstance(arg, ast.Constant):
                                result[expected_params[idx]] = arg.value
                            elif isinstance(arg, ast.Name) and arg.id in symbols:
                                result[expected_params[idx]] = symbols[arg.id]
                    for kw in node.keywords:
                        if kw.arg:
                            if isinstance(kw.value, ast.Constant):
                                result[kw.arg] = kw.value.value
                            elif (
                                isinstance(kw.value, ast.Name)
                                and kw.value.id in symbols
                            ):
                                result[kw.arg] = symbols[kw.value.id]
                    if result:
                        break

    # Normalize common parameter aliases
    if "path" in result and "file_path" not in result:
        result["file_path"] = result["path"]
    if (
        "path" in result
        and "directory_path" not in result
        and tool_name in ("list_directory", "search_file", "delete_directory")
    ):
        result["directory_path"] = result["path"]
    if "dir" in result and "directory_path" not in result:
        result["directory_path"] = result["dir"]
    if "directory" in result and "directory_path" not in result:
        result["directory_path"] = result["directory"]

    return result


def find_structured_candidates(text: str) -> list[tuple[int, int]]:
    """Locate balanced JSON/Python literal bracket candidate spans (start, end)."""
    candidates: list[tuple[int, int]] = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch not in ("{", "["):
            continue
        close_ch = "}" if ch == "{" else "]"
        depth = 0
        in_quote: str | None = None
        escape = False
        for j in range(i, n):
            c = text[j]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if in_quote:
                if c == in_quote:
                    in_quote = None
                continue
            if c in ('"', "'"):
                in_quote = c
                continue
            if c in ("{", "["):
                depth += 1
            elif c in ("}", "]"):
                depth -= 1
                if depth == 0 and c == close_ch:
                    candidates.append((i, j + 1))
                    break
                if depth < 0:
                    break
    return candidates


def try_parse_structured(raw: str) -> tuple[Any | None, str]:
    """Attempt to parse Python dict/list repr or JSON from observation text.

    Returns (parsed_object, extra_text).
    """
    text = raw.strip()
    if not text:
        return None, ""

    # Direct literal_eval
    try:
        val = ast.literal_eval(text)
        if isinstance(val, tuple):
            val = list(val)
        if isinstance(val, (dict, list)):
            return val, ""
    except (ValueError, SyntaxError):
        pass

    # Direct json
    try:
        val = json.loads(text)
        if isinstance(val, (dict, list)):
            return val, ""
    except (json.JSONDecodeError, ValueError):
        pass

    # Embedded balanced bracket search
    candidates = find_structured_candidates(text)
    # Prefer largest outermost structure
    candidates.sort(key=lambda span: span[1] - span[0], reverse=True)

    for start_idx, end_idx in candidates:
        candidate = text[start_idx:end_idx]
        parsed_val = None
        try:
            parsed_val = ast.literal_eval(candidate)
        except (ValueError, SyntaxError):
            pass
        if parsed_val is None:
            try:
                parsed_val = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                pass

        if parsed_val is not None:
            if isinstance(parsed_val, tuple):
                parsed_val = list(parsed_val)
            if isinstance(parsed_val, (dict, list)):
                extra = (text[:start_idx] + "\n" + text[end_idx:]).strip()
                # Clean up dangling output arrow artifacts from logs
                extra = re.sub(r"^\s*->\s*", "", extra)
                extra = re.sub(r"\s*->\s*$", "", extra).strip()
                return parsed_val, extra

    return None, text


def render_directory_tree(
    items_data: list[dict[str, Any] | str] | dict[str, Any] | tuple[Any, ...],
    directory_name: str = ".",
    workspace_root: Path | None = None,
    max_items: int = 35,
) -> Tree:
    """Render filesystem directory items as a sleek, categorized Rich Tree."""
    raw_items: list[Any] = (
        items_data.get("items", [])
        if isinstance(items_data, dict) and "items" in items_data
        else (list(items_data) if isinstance(items_data, (list, tuple)) else [])
    )

    normalized: list[dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, str):
            clean_p = item.rstrip("/\\")
            clean_name = Path(clean_p).name.lower()
            itype = "file"
            if item.endswith(("/", "\\")):
                itype = "directory"
            elif clean_name in KNOWN_EXTENSIONLESS_FILES:
                itype = "file"
            elif workspace_root:
                cand = workspace_root / clean_p
                if cand.is_dir():
                    itype = "directory"
                elif cand.is_file():
                    itype = "file"
            normalized.append({"path": clean_p, "type": itype})
        elif isinstance(item, dict):
            p = str(item.get("path", ""))
            t = str(item.get("type", "file"))
            normalized.append({"path": p, "type": t})

    dirs = [it for it in normalized if it.get("type") in ("directory", "dir")]
    files = [it for it in normalized if it.get("type") not in ("directory", "dir")]
    dirs.sort(key=lambda item: item["path"].lower())
    files.sort(key=lambda item: item["path"].lower())

    # Prefer the supplied query/workspace root, never the first entry's parent.
    # With no root context, a common parent preserves all absolute entry paths.
    requested_root = Path(directory_name or ".")
    base = (
        requested_root
        if requested_root.is_absolute()
        else (workspace_root / requested_root if workspace_root is not None else None)
    )
    paths = [Path(item["path"]) for item in normalized]
    if base is None and paths and all(path.is_absolute() for path in paths):
        base = Path(commonpath([str(path.parent) for path in paths]))
    root_title = directory_name
    if root_title in (".", ""):
        root_title = (base.name or str(base)) if base is not None else "."

    root_label = Text()
    root_label.append(f"📁 {root_title}/ ", style=f"bold {COLOR_INFO}")
    root_label.append(f"({len(dirs)} 目录 · {len(files)} 文件)", style=FG_MUTED)
    tree = Tree(root_label, guide_style=BG_BORDER)
    if not normalized:
        tree.add(Text("(当前范围无条目)", style=FG_MUTED))

    branches: dict[tuple[str, ...], Tree] = {(): tree}
    shown = 0
    for item in [*dirs, *files]:
        if shown >= max_items:
            break
        path = Path(item["path"])
        if path.is_absolute() and base is not None:
            try:
                parts = path.relative_to(base).parts
            except ValueError:
                # Do not pretend an external path is a child of the selected root.
                parts = (str(path),)
        else:
            parts = path.parts
        if not parts or ".." in parts:
            parts = (str(path),)
        is_dir = item["type"] in ("directory", "dir")
        directory_parts = parts if is_dir else parts[:-1]
        for length, part in enumerate(directory_parts, start=1):
            prefix = directory_parts[:length]
            if prefix not in branches:
                label = Text.assemble(
                    ("📁 ", f"bold {COLOR_INFO}"),
                    (f"{part}/", f"bold {FG_PRIMARY}"),
                )
                branches[prefix] = branches[prefix[:-1]].add(label)
        if not is_dir:
            name = parts[-1]
            icon, style_color = get_file_icon_and_style(name)
            if item["type"] == "symlink":
                icon = "↗"
                name += " [符号链接]"
            branches[parts[:-1]].add(Text(f"{icon} {name}", style=style_color))
        shown += 1

    remaining = len(normalized) - shown
    if remaining > 0:
        tree.add(Text(f"… (界面省略其余 {remaining} 项)", style=FG_MUTED))

    if isinstance(items_data, dict):
        for key, label in (
            ("skipped", "概览忽略"),
            ("depth_limited", "达到深度上限，未展开"),
        ):
            paths = items_data.get(key, [])
            if paths:
                tree.add(
                    Text(
                        f"{label}: {len(paths)} 个目录；请定向查询或调整范围",
                        style=FG_MUTED,
                    )
                )
    return tree


def render_search_results(
    results: list[dict[str, Any]] | list[Any] | tuple[Any, ...],
    search_string: str = "",
    workspace_root: Path | None = None,
    max_matches: int = 30,
) -> RenderableType:
    """Render search matches grouped by file in an intuitive tree."""
    if not results:
        return Text("🔍 未找到匹配内容", style=FG_MUTED)

    by_file: dict[str, list[dict[str, Any]]] = {}
    valid_results: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        fpath = str(r.get("file_path", "unknown"))
        by_file.setdefault(fpath, []).append(r)
        valid_results.append(r)

    if not by_file:
        return Text("🔍 未找到匹配内容", style=FG_MUTED)

    root_label = Text()
    root_label.append("🔍 搜索匹配 ", style=f"bold {ACCENT_WARM}")
    root_label.append(
        f"({len(valid_results)} 处匹配 · {len(by_file)} 个文件)", style=f"{FG_MUTED}"
    )

    tree = Tree(root_label, guide_style=BG_BORDER)

    total_shown = 0
    query_re = (
        re.compile(f"({re.escape(search_string)})", re.IGNORECASE)
        if search_string
        else None
    )

    for fpath, matches in by_file.items():
        if total_shown >= max_matches:
            break

        disp_path = fpath
        if workspace_root:
            try:
                disp_path = str(Path(fpath).relative_to(workspace_root))
            except ValueError:
                disp_path = Path(fpath).name
        else:
            disp_path = Path(fpath).name

        fnode = Text()
        fnode.append("📄 ", style=COLOR_INFO)
        fnode.append(disp_path, style=f"bold {FG_PRIMARY}")
        fnode.append(f" ({len(matches)} 处)", style=f"{FG_MUTED}")
        branch = tree.add(fnode)

        for m in matches:
            if total_shown >= max_matches:
                break
            lineno = m.get("line_number", 0)
            text_line = str(m.get("text", m.get("line_content", ""))).strip()

            mnode = Text()
            mnode.append(f"L{lineno:03d} ", style=FG_FAINT)
            mnode.append("│ ", style=BG_BORDER)

            # Highlight search query case-insensitively with preserved text
            if query_re and query_re.search(text_line):
                tokens = query_re.split(text_line)
                for part in tokens:
                    if not part:
                        continue
                    if part.lower() == search_string.lower():
                        mnode.append(part, style=f"bold {ACCENT_WARM}")
                    else:
                        mnode.append(part, style=FG_PRIMARY)
            else:
                mnode.append(text_line, style=FG_PRIMARY)

            branch.add(mnode)
            total_shown += 1

    remaining = len(valid_results) - total_shown
    if remaining > 0:
        tree.add(Text(f"… (界面省略其余 {remaining} 处匹配)", style=FG_MUTED))

    return tree


def render_file_content(
    content: str,
    file_path: str | None = None,
    max_lines: int = 40,
) -> RenderableType:
    """Render file content with syntax highlighting and line numbers."""
    lexer = "text"
    if file_path:
        base_name = Path(file_path).name.lower()
        if base_name in FILENAME_TO_LEXER:
            lexer = FILENAME_TO_LEXER[base_name]
        else:
            suffix = Path(file_path).suffix.lower()
            lexer = EXT_TO_LEXER.get(suffix, "text")

    lines = content.splitlines()
    total_lines = len(lines)

    if total_lines > max_lines:
        preview_text = "\n".join(lines[:max_lines])
        syntax = Syntax(
            preview_text,
            lexer,
            theme=CODE_THEME,
            background_color="default",
            line_numbers=True,
            word_wrap=True,
        )
        notice = Text(
            f"… (共 {total_lines} 行，已展示前 {max_lines} 行) …",
            style=FG_FAINT,
        )
        return Group(syntax, notice)

    return Syntax(
        content,
        lexer,
        theme=CODE_THEME,
        background_color="default",
        line_numbers=True,
        word_wrap=True,
    )


def render_file_diff(
    old_content: str,
    new_content: str,
    file_path: str = "file",
) -> tuple[RenderableType, str]:
    """Generate and syntax-highlight unified diff between old and new file content."""
    fname = Path(file_path).name
    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{fname}",
            tofile=f"b/{fname}",
            lineterm="",
        )
    )
    if not diff_lines:
        return Text("内容未发生变更", style=FG_MUTED), "0 处变更"

    added = sum(
        1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
    )
    diff_str = "\n".join(diff_lines)
    syntax = Syntax(
        diff_str,
        "diff",
        theme=CODE_THEME,
        background_color="default",
        line_numbers=False,
    )
    summary = f"+{added} / -{removed} 行"
    return syntax, summary


def render_data_table(data: Any, max_rows: int = 25) -> Table | None:
    """Attempt to render a list of dictionaries as a clean Rich Table."""
    rows: list[dict[str, Any]] | None = None
    if (
        isinstance(data, (list, tuple))
        and data
        and all(isinstance(x, dict) for x in data)
    ):
        rows = list(data)
    elif isinstance(data, dict):
        # Check if dict has a single key which is a list of dicts
        for v in data.values():
            if (
                isinstance(v, (list, tuple))
                and v
                and all(isinstance(x, dict) for x in v)
            ):
                rows = list(v)
                break

    if not rows:
        return None

    # Collect column names preserving order
    cols: list[str] = []
    for r in rows:
        for k in r:
            if str(k) not in cols:
                cols.append(str(k))
        if len(cols) > 8:
            break

    if not cols:
        return None

    table = Table(
        box=box.SIMPLE_HEAD,
        show_edge=False,
        header_style=f"bold {ACCENT_WARM}",
        expand=True,
    )
    for col in cols:
        table.add_column(col.capitalize(), style=FG_PRIMARY)

    for i, row in enumerate(rows):
        if i >= max_rows:
            table.add_row(
                *(
                    f"… (+{len(rows) - max_rows} 项)" if j == 0 else ""
                    for j in range(len(cols))
                )
            )
            break
        table.add_row(
            *(str("" if row.get(col) is None else row.get(col)) for col in cols)
        )

    return table


def render_tool_call_card(tool_name: str, code_or_args: str) -> Panel:
    """Render a tool call request in a Codex-style card container with syntax highlighting."""
    title = Text()
    title.append("▸ ", style=f"bold {ACCENT_WARM}")
    title.append(
        "执行 Python" if tool_name == "python_interpreter" else "调用工具",
        style=f"bold {ACCENT_WARM}",
    )
    title.append(f" [{tool_name}]", style=f"bold {FG_PRIMARY}")

    cleaned = code_or_args.strip()

    # 1. JSON formatting
    if cleaned.startswith(("{", "[")):
        try:
            val = json.loads(cleaned)
            pretty = json.dumps(val, indent=2, ensure_ascii=False)
            body: RenderableType = Syntax(
                pretty,
                "json",
                theme=CODE_THEME,
                background_color="default",
                line_numbers=False,
                word_wrap=True,
            )
            return Panel(
                body,
                title=title,
                title_align="left",
                border_style=BG_BORDER,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        except (ValueError, SyntaxError, TypeError):
            pass

    # 2. Python AST or code heuristic
    is_python = False
    if tool_name == "python_interpreter":
        is_python = True
    else:
        try:
            ast.parse(cleaned)
            is_python = True
        except SyntaxError:
            if (
                "(" in cleaned
                and ")" in cleaned
                or any(
                    kw in cleaned
                    for kw in (
                        "def ",
                        "import ",
                        "=",
                        "print(",
                        "for ",
                        "if ",
                        "return ",
                    )
                )
            ):
                is_python = True

    if is_python:
        body = Syntax(
            cleaned,
            "python",
            theme=CODE_THEME,
            background_color="default",
            line_numbers=False,
            word_wrap=True,
        )
    else:
        body = Text(cleaned, style=FG_PRIMARY)

    return Panel(
        body,
        title=title,
        title_align="left",
        border_style=BG_BORDER,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def render_tool_result_card(
    observation: str,
    duration: float | None = None,
    is_error: bool = False,
    tool_context: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> Panel:
    """Render observation or tool output in a Codex-style structured card container."""
    title = Text()
    if is_error:
        title.append("! ", style=f"bold {COLOR_DANGER}")
        title.append("执行异常", style=f"bold {COLOR_DANGER}")
    else:
        title.append("✓ ", style=f"bold {COLOR_SUCCESS}")
        title.append("观察结果", style=f"bold {COLOR_SUCCESS}")
    if duration is not None and duration > 0:
        title.append(f"  ·  步骤耗时 {duration:.1f}s", style=f"{FG_MUTED}")

    if is_error:
        return Panel(
            Text(observation.strip(), style=COLOR_DANGER),
            title=title,
            title_align="left",
            border_style=COLOR_DANGER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    tool_name = (tool_context or {}).get("tool_name", "")
    extracted_args = (tool_context or {}).get("extracted_args", {})
    parsed, extra_logs = try_parse_structured(observation)

    # 1. SPECIFIC TOOL ROUTING: Prioritize explicit tool intent over heuristic guessing

    # A. File Content: read_file tool output (MUST precede items/results heuristic)
    if tool_name == "read_file":
        fpath = str(extracted_args.get("file_path", ""))
        file_text = observation
        prefix_logs = ""
        if "\n\n-> " in observation:
            prefix_logs, file_text = observation.split("\n\n-> ", 1)
        elif parsed is not None and extra_logs:
            prefix_logs = extra_logs

        rendered_code = render_file_content(file_text, file_path=fpath)
        content: RenderableType = (
            Group(Text(prefix_logs.strip(), style=FG_MUTED), rendered_code)
            if prefix_logs.strip()
            else rendered_code
        )
        total_lines = len(file_text.splitlines())
        subtitle = (
            Text(f" 📄 {Path(fpath).name} · {total_lines} 行 ", style=FG_FAINT)
            if fpath
            else None
        )
        return Panel(
            content,
            title=title,
            subtitle=subtitle,
            subtitle_align="right",
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # B. Directory Tree: list_directory tool
    if tool_name == "list_directory":
        dir_name = extracted_args.get("directory_path", ".")
        tree = render_directory_tree(
            parsed if parsed is not None else [],
            directory_name=dir_name,
            workspace_root=workspace_root,
        )
        content = (
            Group(Text(extra_logs, style=FG_MUTED), tree)
            if (parsed is not None and extra_logs)
            else tree
        )
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # C. Search Results: search_file tool
    if tool_name == "search_file":
        s_query = str(extracted_args.get("search_string", ""))
        raw_res = (
            parsed.get("results", [])
            if isinstance(parsed, dict)
            else (parsed if isinstance(parsed, (list, tuple)) else [])
        )
        tree = render_search_results(
            raw_res, search_string=s_query, workspace_root=workspace_root
        )
        content = (
            Group(Text(extra_logs, style=FG_MUTED), tree)
            if (parsed is not None and extra_logs)
            else tree
        )
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # D. File Edit: edit_file diff presentation
    if tool_name == "edit_file":
        if "old_content" in extracted_args and "new_content" in extracted_args:
            fpath = str(extracted_args.get("file_path", "file"))
            diff_syntax, diff_summary = render_file_diff(
                str(extracted_args["old_content"]),
                str(extracted_args["new_content"]),
                file_path=fpath,
            )
            bytes_w = parsed.get("bytes_written", 0) if isinstance(parsed, dict) else 0
            bytes_note = f" · 写入 {bytes_w} 字节" if bytes_w else ""
            subtitle = Text(
                f" 📄 {Path(fpath).name} · {diff_summary}{bytes_note} ",
                style=FG_FAINT,
            )
            return Panel(
                diff_syntax,
                title=title,
                subtitle=subtitle,
                subtitle_align="right",
                title_align="left",
                border_style=BG_BORDER,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        if isinstance(parsed, dict) and "path" in parsed:
            fname = Path(str(parsed["path"])).name
            bytes_w = parsed.get("bytes_written", 0)
            res_text = Text.assemble(
                ("✓ ", f"bold {COLOR_SUCCESS}"),
                ("文件已更新: ", f"bold {COLOR_SUCCESS}"),
                (fname, f"bold {FG_PRIMARY}"),
                (f" (写入 {bytes_w} 字节)", f"{FG_MUTED}"),
            )
            return Panel(
                res_text,
                title=title,
                title_align="left",
                border_style=BG_BORDER,
                box=box.ROUNDED,
                padding=(0, 1),
            )

    # E. File Creation: create_file preview
    if tool_name == "create_file":
        fpath = str(
            extracted_args.get("file_path")
            or (parsed.get("path", "") if isinstance(parsed, dict) else "")
        )
        fname = Path(fpath).name if fpath else "新文件"
        bytes_w = parsed.get("bytes_written", 0) if isinstance(parsed, dict) else 0
        header_text = Text.assemble(
            ("✓ ", f"bold {COLOR_SUCCESS}"),
            ("文件已创建: ", f"bold {COLOR_SUCCESS}"),
            (fname, f"bold {FG_PRIMARY}"),
            (f" (写入 {bytes_w} 字节)", f"{FG_MUTED}"),
        )
        content_created = str(extracted_args.get("content", "")).strip()
        if content_created:
            preview = render_file_content(
                content_created, file_path=fname, max_lines=20
            )
            content = Group(header_text, Text(""), preview)
        else:
            content = header_text
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # F. File/Directory Deletion: delete_file / delete_directory
    if tool_name in ("delete_file", "delete_directory") or (
        isinstance(parsed, dict) and parsed.get("deleted") is True
    ):
        tpath = str(
            (parsed.get("path") if isinstance(parsed, dict) else None)
            or extracted_args.get("file_path")
            or extracted_args.get("directory_path", "")
        )
        is_dir = tool_name == "delete_directory" or (
            isinstance(parsed, dict) and "directory" in str(parsed.get("path", ""))
        )
        item_label = "目录" if is_dir else "文件"
        fname = Path(tpath).name if tpath else item_label
        del_text = Text.assemble(
            ("🗑 ", f"bold {COLOR_WARNING}"),
            (f"已删除{item_label}: ", f"bold {COLOR_WARNING}"),
            (fname, f"bold {FG_PRIMARY}"),
        )
        return Panel(
            del_text,
            title=title,
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # 2. GENERIC STRUCTURE DETECTION: Fallback structure matching for generic tool outputs

    # Structure 1: Directory Tree (verify that items actually represent filesystem entries)
    if (
        isinstance(parsed, dict)
        and "items" in parsed
        and isinstance(parsed["items"], (list, tuple))
    ):
        items_list = list(parsed["items"])
        if all(
            isinstance(x, dict) and ("path" in x or "type" in x) for x in items_list
        ):
            dir_name = extracted_args.get("directory_path", ".")
            tree = render_directory_tree(
                parsed, directory_name=dir_name, workspace_root=workspace_root
            )
            content = (
                Group(Text(extra_logs, style=FG_MUTED), tree) if extra_logs else tree
            )
            return Panel(
                content,
                title=title,
                title_align="left",
                border_style=BG_BORDER,
                box=box.ROUNDED,
                padding=(0, 1),
            )

    # Structure 2: Search Results (verify that results actually represent file search matches)
    if (
        isinstance(parsed, dict)
        and "results" in parsed
        and isinstance(parsed["results"], (list, tuple))
    ):
        res_list = list(parsed["results"])
        if res_list and all(isinstance(x, dict) and "file_path" in x for x in res_list):
            s_query = str(extracted_args.get("search_string", ""))
            tree = render_search_results(
                res_list, search_string=s_query, workspace_root=workspace_root
            )
            content = (
                Group(Text(extra_logs, style=FG_MUTED), tree) if extra_logs else tree
            )
            return Panel(
                content,
                title=title,
                title_align="left",
                border_style=BG_BORDER,
                box=box.ROUNDED,
                padding=(0, 1),
            )

    # Structure 3: Tabular structured data
    tbl = render_data_table(parsed)
    if tbl is not None:
        content = Group(Text(extra_logs, style=FG_MUTED), tbl) if extra_logs else tbl
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # Structure 4: General JSON / Dict / List representation
    if isinstance(parsed, (dict, list, tuple)):
        json_str = json.dumps(parsed, indent=2, ensure_ascii=False)
        json_syn = Syntax(
            json_str,
            "json",
            theme=CODE_THEME,
            background_color="default",
            line_numbers=False,
            word_wrap=True,
        )
        content = (
            Group(Text(extra_logs, style=FG_MUTED), json_syn)
            if extra_logs
            else json_syn
        )
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=BG_BORDER,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    # 3. Fallback: Clean text representation
    return Panel(
        Text(observation.strip(), style=FG_PRIMARY),
        title=title,
        title_align="left",
        border_style=BG_BORDER,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def render_thought_card(thought: str, duration: float | None = None) -> Panel:
    """Render an agent thought trace in a sleek, muted panel."""
    title = Text()
    title.append("◇ ", style=f"bold {COLOR_INFO}")
    title.append("思考过程", style=f"bold {COLOR_INFO}")
    if duration is not None and duration > 0:
        title.append(f"  ·  {duration:.1f}s", style=f"{FG_MUTED}")

    return Panel(
        Text(thought.strip(), style=FG_MUTED),
        title=title,
        title_align="left",
        border_style=BG_BORDER,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def render_plan_card(plan: str, duration: float | None = None) -> Panel:
    """Render an agent task plan in an amber-accented panel."""
    title = Text()
    title.append("📋 ", style=f"bold {ACCENT_WARM}")
    title.append("任务规划", style=f"bold {ACCENT_WARM}")
    if duration is not None and duration > 0:
        title.append(f"  ·  {duration:.1f}s", style=f"{FG_MUTED}")

    return Panel(
        Markdown(plan.strip(), code_theme=CODE_THEME, style=FG_PRIMARY),
        title=title,
        title_align="left",
        border_style=BG_BORDER,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def render_error_card(error_msg: str, duration: float | None = None) -> Panel:
    """Render an application error in an attention-calling coral red panel."""
    title = Text()
    title.append("! ", style=f"bold {COLOR_DANGER}")
    title.append("错误", style=f"bold {COLOR_DANGER}")
    if duration is not None and duration > 0:
        title.append(f"  ·  {duration:.1f}s", style=f"{FG_MUTED}")

    return Panel(
        Text(error_msg.strip(), style=COLOR_DANGER),
        title=title,
        title_align="left",
        border_style=COLOR_DANGER,
        box=box.ROUNDED,
        padding=(0, 1),
    )
