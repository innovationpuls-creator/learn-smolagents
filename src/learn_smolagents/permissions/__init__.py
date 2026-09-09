"""File access coordination and authorization policy."""

from .access import FileAccess
from .policy import check_permission

__all__ = ["FileAccess", "check_permission"]
