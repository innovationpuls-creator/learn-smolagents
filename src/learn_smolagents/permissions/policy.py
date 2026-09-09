from pathlib import Path


def check_permission(
    target: Path, workspace_root: Path, full_access: bool = False
) -> str:
    if full_access:
        return "allow"
    if target.resolve().is_relative_to(workspace_root.resolve(strict=False)):
        return "allow"
    else:
        return "ask"
