"""Formatting functions for conversation timeline headers and messages."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from learn_smolagents.ui.theme.tokens import (
    ACCENT_WARM,
    BG_BASE,
    BG_BORDER,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_SUCCESS,
    FG_FAINT,
    FG_MUTED,
    FG_PRIMARY,
)


def format_timestamp() -> str:
    """Return current time formatted as HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


def format_user_turn_header(turn: int) -> Text:
    """Render user turn header with elegant tag and timestamp."""
    header = Text()
    header.append("❯ ", style=f"bold {ACCENT_WARM}")
    header.append(f"你  #{turn:02d}", style=f"bold {ACCENT_WARM}")
    header.append(f"  ·  {format_timestamp()}", style=f"{FG_FAINT}")
    return header


def format_agent_turn_header(elapsed: float | None = None) -> Text:
    """Render Agent response header with refined brand pill."""
    header = Text()
    header.append("✳ ", style=f"bold {COLOR_SUCCESS}")
    header.append("Agent", style=f"bold {COLOR_SUCCESS}")
    if elapsed is not None and elapsed > 0:
        header.append(f"  ·  {elapsed:.1f}s", style=f"{FG_MUTED}")
    header.append(f"  ·  {format_timestamp()}", style=f"{FG_FAINT}")
    return header


def format_thought_header(elapsed: float | None = None) -> Text:
    """Render thought header with tree branch guide."""
    header = Text()
    header.append("│  ", style=f"{BG_BORDER}")
    header.append("◇ ", style=f"bold {COLOR_INFO}")
    header.append("思考过程", style=f"bold {COLOR_INFO}")
    if elapsed is not None and elapsed > 0:
        header.append(f"  ·  {elapsed:.1f}s", style=f"{FG_MUTED}")
    return header


def format_tool_header(tool_name: str, duration: float | None = None) -> Text:
    """Render tool execution observation header."""
    header = Text()
    header.append("│  ", style=f"{BG_BORDER}")
    header.append("▸ ", style=f"bold {ACCENT_WARM}")
    header.append("工具调用", style=f"bold {ACCENT_WARM}")
    header.append(f" [{tool_name}]", style=f"bold {FG_PRIMARY}")
    header.append("  ✓ 观察结果", style=f"{COLOR_SUCCESS}")
    if duration is not None and duration > 0:
        header.append(f"  ·  {duration:.1f}s", style=f"{FG_MUTED}")
    return header


def format_error_header() -> Text:
    """Render error header."""
    header = Text()
    header.append("! ", style=f"bold {COLOR_DANGER}")
    header.append("错误", style=f"bold {COLOR_DANGER}")
    header.append(f"  ·  {format_timestamp()}", style=f"{FG_FAINT}")
    return header


def format_timeline_body(content: str, prefix: str = "│  ", style: str = FG_PRIMARY) -> Text:
    """Format multiline body text with a timeline branch prefix."""
    lines = content.splitlines()
    if not lines:
        return Text(prefix, style=f"{BG_BORDER}")
    text = Text()
    for i, line in enumerate(lines):
        text.append(prefix, style=f"{BG_BORDER}")
        text.append(line, style=style)
        if i < len(lines) - 1:
            text.append("\n")
    return text
