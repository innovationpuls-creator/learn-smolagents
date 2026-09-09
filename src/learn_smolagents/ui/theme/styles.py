"""Pygments syntax highlighter style and Rich Markdown themes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, cast

from pygments.style import Style as PygmentsStyle
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    String,
    Token,
    _TokenType,
)
from rich.syntax import PygmentsSyntaxTheme
from rich.theme import Theme

from learn_smolagents.ui.theme.tokens import (
    ACCENT_ROSE,
    ACCENT_SOFT,
    ACCENT_WARM,
    BG_BORDER,
    BG_SURFACE,
    COLOR_INFO,
    COLOR_SUCCESS,
    FG_MUTED,
    FG_PRIMARY,
)


class WarmGruvboxStyle(PygmentsStyle):
    """Pygments syntax style tailored to the Gruvbox Material terminal palette."""

    background_color = BG_SURFACE
    styles: ClassVar[Mapping[_TokenType, str]] = {
        Token: FG_PRIMARY,
        Comment: f"italic {FG_MUTED}",
        Keyword: f"bold {ACCENT_WARM}",
        Name: FG_PRIMARY,
        Name.Function: f"bold {COLOR_SUCCESS}",
        Name.Builtin: COLOR_INFO,
        Number: ACCENT_SOFT,
        Operator: ACCENT_WARM,
        String: COLOR_SUCCESS,
    }


CODE_THEME: str = cast(str, cast(object, PygmentsSyntaxTheme(WarmGruvboxStyle)))

MARKDOWN_THEME = Theme(
    {
        "markdown.h1": f"bold {FG_PRIMARY}",
        "markdown.h1.border": ACCENT_WARM,
        "markdown.h2": f"bold {ACCENT_WARM}",
        "markdown.h3": f"bold {ACCENT_ROSE}",
        "markdown.h4": f"bold {FG_PRIMARY}",
        "markdown.code": f"{ACCENT_WARM} on {BG_SURFACE}",
        "markdown.code_block": FG_PRIMARY,
        "markdown.block_quote": f"italic {FG_MUTED}",
        "markdown.list": ACCENT_WARM,
        "markdown.item.number": ACCENT_WARM,
        "markdown.link": f"underline {COLOR_INFO}",
        "markdown.link_url": f"underline {COLOR_INFO}",
        "markdown.table.border": BG_BORDER,
        "markdown.table.header": f"bold {FG_PRIMARY}",
    }
)
