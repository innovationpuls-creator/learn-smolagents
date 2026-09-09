from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ApprovalScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "deny", "拒绝")]
    DEFAULT_CSS = """
    ApprovalScreen { align: center middle; background: #201e1b 85%; }
    #approval-dialog { width: 72; max-width: 95%; height: auto; max-height: 90%; padding: 1 2; border: round #d99778; background: #292520; color: #e8dfd1; }
    #approval-dialog Static { height: auto; margin-bottom: 1; }
    #approval-dialog Horizontal { height: 3; }
    #approval-dialog Button { width: 1fr; background: #393029; color: #e8dfd1; border: none; }
    """

    def __init__(self, target, operation):
        super().__init__()
        self.target = target
        self.operation = operation

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="approval-dialog"):
            yield Static("请求访问工作区外的路径")
            yield Static(f"操作：{self.operation}\n路径：{self.target}", markup=False)
            with Horizontal():
                yield Button("拒绝 Esc", id="deny-access")
                yield Button("本次允许", id="allow-access")

    def on_mount(self):
        self.query_one("#deny-access", Button).focus()

    def on_button_pressed(self, event):
        event.stop()
        self.dismiss(event.button.id == "allow-access")

    def action_deny(self):
        self.dismiss(False)
