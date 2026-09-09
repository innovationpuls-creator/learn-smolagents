from pathlib import Path


class Workspace:
    def __init__(self, root_path: Path | None):
        self.root = None
        if root_path is not None:
            self.switch(root_path)

    def switch(self, root_path: Path) -> None:
        """切换至已存在的目录；验证失败时保留原工作区。"""
        target = root_path.resolve(strict=True)
        if not target.is_dir():
            raise ValueError(f"指定的路径不是目录: {target}")
        self.root = target

    def resolve(self, relative_path: str) -> Path:
        """
        解析绝对路径，相对路径以工作区为起点.
        Args:
            relative_path: 相对于工作区根目录的路径。
        returns:
            解析后的绝对路径。
        """
        if self.root is None:
            raise ValueError("请先选择工作区")
        target = Path(relative_path)
        if not target.is_absolute():
            target = self.root / target
        return target.resolve(strict=False)
