"""Environment selection and local application settings."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def config_directory() -> Path:
    environment = os.environ.get("LEARN_SMOLAGENTS_ENV", "development")
    if environment not in {"development", "test", "production"}:
        raise ValueError("LEARN_SMOLAGENTS_ENV 必须是 development、test 或 production")
    root = Path(
        os.environ.get(
            "LEARN_SMOLAGENTS_CONFIG_DIR", str(Path.home() / ".config/learn-smolagents")
        )
    )
    return root / environment


@dataclass(frozen=True)
class LLMConfig:
    model_id: str = ""
    api_base: str = ""
    api_key: str = ""

    def validate(self) -> None:
        from urllib.parse import urlparse

        if not self.model_id.strip() or not self.api_key.strip():
            raise ValueError("请在 LLM 配置中填写模型名称和 API 密钥")
        parsed = urlparse(self.api_base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("API 地址必须是完整的 HTTP 或 HTTPS 地址")


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else config_directory() / "llm.json"

    def load(self) -> LLMConfig:
        if not self.path.exists():
            return LLMConfig()
        return LLMConfig(**json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, config: LLMConfig) -> None:
        config.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
        temporary.replace(self.path)
