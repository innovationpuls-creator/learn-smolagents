"""Modal screens package for Local CodeAgent."""

from learn_smolagents.ui.screens.approval import ApprovalScreen
from learn_smolagents.ui.screens.settings import SettingsScreen
from learn_smolagents.ui.screens.workspaces import (
    DeleteWorkspaceScreen,
    WorkspaceManager,
)

__all__ = [
    "ApprovalScreen",
    "DeleteWorkspaceScreen",
    "SettingsScreen",
    "WorkspaceManager",
]
