from pathlib import Path

from learn_smolagents.workspace import Workspace

from .policy import check_permission


class FileAccess:
    def __init__(self, workspace: Workspace, full_access: bool = False, approval=None):
        self.approval = approval
        self.workspace = workspace
        self.full_access = full_access

    def check_permission(self, path: str, operation: str) -> Path:
        target = self.workspace.resolve(path)
        decision = check_permission(target, self.workspace.root, self.full_access)
        if decision == "allow":
            return target
        elif decision == "ask":
            if self.approval is not None:
                if self.approval(target, operation):
                    return target
                raise PermissionError(f"用户拒绝{operation}：{target}")
            answer = input(
                f"\nAgent 请求执行：{operation}\n"
                f"目标路径：{target}\n"
                "是否允许本次操作？输入 y 批准，其他输入拒绝："
            )
            if answer.strip().lower() == "y":
                return target

            raise PermissionError(f"用户拒绝{operation}：{target}")

        raise ValueError(f"无法识别的权限判断结果：{decision}")
