"""Modern, modular UI package for Local CodeAgent."""

from learn_smolagents.ui.app import LocalCodeAgentApp
from learn_smolagents.ui.renderers import (
    extract_tool_arguments,
    render_directory_tree,
    render_error_card,
    render_file_content,
    render_file_diff,
    render_plan_card,
    render_search_results,
    render_thought_card,
    render_tool_call_card,
    render_tool_result_card,
)
from learn_smolagents.ui.router import Route, UIRouter

__all__ = [
    "LocalCodeAgentApp",
    "Route",
    "UIRouter",
    "extract_tool_arguments",
    "render_directory_tree",
    "render_error_card",
    "render_file_content",
    "render_file_diff",
    "render_plan_card",
    "render_search_results",
    "render_thought_card",
    "render_tool_call_card",
    "render_tool_result_card",
]
