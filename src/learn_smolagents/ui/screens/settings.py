"""LLM configuration modal screen with provider presets and connection testing."""

from __future__ import annotations

import urllib.request
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from learn_smolagents.config import LLMConfig, SettingsStore
from learn_smolagents.ui.theme import (
    BG_BASE,
    BG_BORDER,
    BG_BORDER_FOCUS,
    BG_OVERLAY,
    COLOR_DANGER,
    COLOR_INFO,
    FG_MUTED,
    FG_PRIMARY,
)

PRESETS: dict[str, tuple[str, str]] = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
    "ollama": ("http://localhost:11434/v1", "qwen2.5-coder:7b"),
    "lmstudio": ("http://localhost:1234/v1", "qwen2.5-coder-7b-instruct"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V3"),
}


class SettingsScreen(ModalScreen[LLMConfig | None]):
    """Modal screen for editing LLM settings with presets and connection testing."""

    BINDINGS: ClassVar = [("escape", "cancel", "取消")]
    DEFAULT_CSS = f"""
    SettingsScreen {{
        align: center middle;
        background: {BG_BASE} 80%;
    }}
    #llm-dialog {{
        width: 68;
        max-width: 95%;
        height: auto;
        padding: 1 2;
        background: {BG_OVERLAY};
        border: round {BG_BORDER_FOCUS};
    }}
    #llm-title {{
        text-style: bold;
        color: {BG_BORDER_FOCUS};
        height: 1;
    }}
    .setting-label {{
        color: {FG_MUTED};
        height: 1;
        margin-top: 0;
    }}
    .preset-row {{
        height: 1;
        margin-bottom: 0;
    }}
    .preset-row Button {{
        height: 1;
        padding: 0 1;
        margin-right: 1;
        border: none;
        background: #3c3836;
        color: {FG_PRIMARY};
    }}
    .preset-row Button:hover {{
        background: #504945;
    }}
    #llm-dialog Input {{
        height: 1;
        margin: 0;
        padding: 0 1;
        background: {BG_BASE};
        border: none;
        color: {FG_PRIMARY};
    }}
    #llm-dialog Input:focus {{
        background: #32302f;
    }}
    #llm-error {{
        height: auto;
        color: {COLOR_DANGER};
    }}
    #llm-test-result {{
        height: auto;
        color: {COLOR_INFO};
    }}
    .action-row {{
        height: 3;
        margin-top: 1;
    }}
    .action-row Button {{
        width: 1fr;
        height: 3;
        border: none;
        margin-right: 1;
        background: #3c3836;
        color: {FG_PRIMARY};
    }}
    #llm-save {{
        background: {BG_BORDER_FOCUS};
        color: {BG_BASE};
        text-style: bold;
    }}
    #llm-save:hover {{
        background: #ff9933;
    }}
    #llm-cancel:hover {{
        background: #504945;
    }}
    #llm-test {{
        background: #458588;
        color: {BG_BASE};
    }}
    """

    def __init__(self, store: SettingsStore) -> None:
        super().__init__()
        self.store = store
        self.config = store.load()

    def compose(self) -> ComposeResult:
        with Vertical(id="llm-dialog"):
            yield Static("⚙  LLM 服务配置", id="llm-title")
            
            with Horizontal(classes="preset-row"):
                yield Button("DeepSeek", id="preset-deepseek")
                yield Button("OpenAI", id="preset-openai")
                yield Button("Ollama", id="preset-ollama")
                yield Button("LM Studio", id="preset-lmstudio")
                yield Button("硅基流动", id="preset-siliconflow")

            yield Static("模型名称 (Model ID)", classes="setting-label")
            yield Input(self.config.model_id, placeholder="例如：deepseek-chat 或 gpt-4o", id="llm-model")
            
            yield Static("API 地址 (Base URL)", classes="setting-label")
            yield Input(self.config.api_base, placeholder="例如：https://api.deepseek.com", id="llm-base")
            
            yield Static("API 密钥 (API Key)", classes="setting-label")
            yield Input(self.config.api_key, password=True, placeholder="留空或填入 sk-...", id="llm-key")

            yield Static("", id="llm-error", markup=False)
            yield Static("", id="llm-test-result", markup=False)

            with Horizontal(classes="action-row"):
                yield Button("测试连通", id="llm-test")
                yield Button("取消 Esc", id="llm-cancel")
                yield Button("保存配置", id="llm-save")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        button_id = event.button.id
        if not button_id:
            return

        if button_id.startswith("preset-"):
            preset_key = button_id.replace("preset-", "")
            if preset_key in PRESETS:
                api_base, model_id = PRESETS[preset_key]
                self.query_one("#llm-base", Input).value = api_base
                self.query_one("#llm-model", Input).value = model_id
                self.query_one("#llm-test-result", Static).update(f"已填充 {preset_key} 预设")
            return

        if button_id == "llm-cancel":
            self.dismiss(None)
            return

        if button_id == "llm-test":
            self._test_connection()
            return

        if button_id == "llm-save":
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

    @work(thread=True)
    def _test_connection(self) -> None:
        base_url = self.query_one("#llm-base", Input).value.strip()
        api_key = self.query_one("#llm-key", Input).value.strip()
        if not base_url:
            self.app.call_from_thread(
                self.query_one("#llm-test-result", Static).update, "! 请先填写 API 地址"
            )
            return

        self.app.call_from_thread(
            self.query_one("#llm-test-result", Static).update, "正在测试连通性..."
        )
        url = base_url.rstrip("/") + "/models"
        req = urllib.request.Request(url, headers={"User-Agent": "learn-smolagents-tui"})
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        try:
            with urllib.request.urlopen(req, timeout=3.5) as response:
                status = response.status
                self.app.call_from_thread(
                    self.query_one("#llm-test-result", Static).update,
                    f"✓ 连通成功 (HTTP {status})",
                )
        except Exception as err:
            self.app.call_from_thread(
                self.query_one("#llm-test-result", Static).update,
                f"ℹ 连接测试反馈: {err}",
            )
