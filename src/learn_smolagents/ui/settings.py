"""LLM settings editor."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from learn_smolagents.config import LLMConfig, SettingsStore


class SettingsScreen(ModalScreen[LLMConfig | None]):
    BINDINGS: ClassVar = [("escape", "cancel", "取消")]
    DEFAULT_CSS = """
    SettingsScreen { align: center middle; }
    #llm-dialog { width: 64; max-width: 95%; height: auto; max-height: 95%;
        overflow-y: auto; padding: 1 2; background: #292520; }
    #llm-dialog Input { margin-bottom: 1; }
    #llm-error { height: auto; color: #e4a293; }
    """

    def __init__(self, store: SettingsStore):
        super().__init__()
        self.store = store
        self.config = store.load()

    def compose(self) -> ComposeResult:
        with Vertical(id="llm-dialog"):
            yield Static("LLM 配置 · 保存后开启新会话")
            yield Static("模型名称")
            yield Input(self.config.model_id, id="llm-model")
            yield Static("API 地址")
            yield Input(self.config.api_base, id="llm-base")
            yield Static("API 密钥（保存在本机配置文件）")
            yield Input(self.config.api_key, password=True, id="llm-key")
            yield Static("", id="llm-error", markup=False)
            yield Button("保存", id="llm-save")
            yield Button("取消", id="llm-cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "llm-cancel":
            self.dismiss(None)
        elif event.button.id == "llm-save":
            config = LLMConfig(
                self.query_one("#llm-model", Input).value.strip(),
                self.query_one("#llm-base", Input).value.strip(),
                self.query_one("#llm-key", Input).value.strip(),
            )
            try:
                self.store.save(config)
            except (ValueError, OSError) as error:
                self.query_one("#llm-error", Static).update(str(error))
                return
            self.dismiss(config)
