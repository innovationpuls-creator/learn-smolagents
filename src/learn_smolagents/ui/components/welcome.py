"""Welcome screen component featuring braille mark and quick guidance."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from resvg_py import svg_to_bytes
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from learn_smolagents.ui.theme import ACCENT_WARM, FG_MUTED, FG_PRIMARY


def render_mark(columns: int, rows: int) -> Text:
    """Rasterize the SVG into 2-by-4 dot cells, without blurred color blocks."""
    png = svg_to_bytes(
        svg_path=str(Path(__file__).parent.parent.parent / "assets" / "smol-mark.svg"),
        width=columns * 2,
        height=rows * 4,
    )
    with Image.open(BytesIO(png)) as image:
        alpha = image.convert("RGBA").getchannel("A")
        dots = (
            (0, 0, 1),
            (0, 1, 2),
            (0, 2, 4),
            (1, 0, 8),
            (1, 1, 16),
            (1, 2, 32),
            (0, 3, 64),
            (1, 3, 128),
        )
        lines = []
        for row in range(rows):
            line = []
            for column in range(columns):

                def is_opaque(x: int, y: int) -> bool:
                    value = alpha.getpixel((x, y))
                    return isinstance(value, (int, float)) and value >= 64

                mask = sum(
                    bit for x, y, bit in dots if is_opaque(column * 2 + x, row * 4 + y)
                )
                line.append(chr(0x2800 + mask) if mask else " ")
            lines.append("".join(line))
    return Text("\n".join(lines), style=ACCENT_WARM)


class WelcomeView(Vertical):
    """Empty state welcome lockup with rasterized graphic and greeting copy."""

    DEFAULT_CSS = f"""
    WelcomeView {{
        height: 1fr;
        align: center middle;
    }}
    #welcome-lockup {{
        width: 70;
        max-width: 100%;
        height: 12;
        align-vertical: middle;
    }}
    #sigil {{
        height: 12;
        width: 24;
        margin-right: 4;
    }}
    #welcome-copy {{
        width: 1fr;
        height: 6;
        margin-top: 3;
    }}
    #eyebrow {{
        height: 2;
        color: {ACCENT_WARM};
        text-style: bold;
    }}
    #greeting {{
        height: 2;
        text-style: bold;
        color: {FG_PRIMARY};
    }}
    #intro {{
        height: 2;
        color: {FG_MUTED};
    }}
    Screen.compact WelcomeView {{
        height: 6;
    }}
    Screen.compact #sigil {{
        height: 6;
        width: 12;
        margin-right: 2;
    }}
    Screen.compact #welcome-lockup {{
        height: 6;
    }}
    Screen.compact #welcome-copy {{
        height: 5;
        margin-top: 1;
    }}
    Screen.compact #eyebrow {{
        height: 1;
    }}
    Screen.compact #intro {{
        height: 1;
    }}
    Screen.compact #greeting {{
        height: 1;
    }}
    """

    def __init__(self, id: str = "welcome") -> None:
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        with Horizontal(id="welcome-lockup"):
            yield Static(render_mark(24, 12), id="sigil")
            with Vertical(id="welcome-copy"):
                yield Static("LOCAL / CODEAGENT", id="eyebrow", markup=False)
                yield Static("从一个问题开始。", id="greeting", markup=False)
                yield Static("输入消息，开始对话。", id="intro", markup=False)

    def update_size(self, compact: bool) -> None:
        sigil = self.query_one("#sigil", Static)
        sigil.update(render_mark(12, 6) if compact else render_mark(24, 12))
