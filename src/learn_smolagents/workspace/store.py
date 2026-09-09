from pathlib import Path

from learn_smolagents.config import config_directory


class WorkspaceStore:
    """保存 TUI 的工作区列表和当前选择。"""

    def __init__(self, config_path=None, initial=None):
        import json

        self.config_path = config_path or config_directory() / "workspaces.json"
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.paths = [Path(value) for value in data["paths"]]
            self.current = Path(data["current"]) if data["current"] else None
        else:
            self.current = (initial or Path.cwd()).resolve(strict=True)
            self.paths = [self.current]

    def _save(self):
        import json

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "paths": [str(p) for p in self.paths],
                    "current": str(self.current) if self.current else None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.config_path)

    def open(self, value, *, create=False):
        path = Path(value.strip()).expanduser()
        if not value.strip() or not path.is_absolute():
            raise ValueError("请输入工作区绝对路径")
        path = path.resolve()
        if create:
            path.mkdir(parents=True, exist_ok=False)
        if not path.is_dir():
            raise ValueError("工作区目录不存在")
        if path not in self.paths:
            self.paths.append(path)
        self.current = path
        self._save()
        return path

    def delete(self, path, confirmation):
        import shutil

        if path not in self.paths or confirmation != path.name:
            raise ValueError("请输入选中工作区的名称确认删除")
        if path.is_symlink():
            raise ValueError("不能删除符号链接工作区")
        resolved = path.resolve()
        protected = (
            Path(__file__).resolve().parent.parent,
            Path.cwd().resolve(),
            Path.home().resolve(),
            self.config_path.parent.resolve(),
        )
        if any(item == resolved or item.is_relative_to(resolved) for item in protected):
            raise ValueError("不能删除程序、启动、主目录、配置目录或其上级目录")
        if path.exists():
            shutil.rmtree(path)
        self.paths = [p for p in self.paths if not p.is_relative_to(path)]
        if self.current not in self.paths:
            self.current = None
        self._save()
