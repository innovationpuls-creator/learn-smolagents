"""Color tokens and design system constants for Gruvbox Material Dark."""

from __future__ import annotations

# Core Palette: Gruvbox Material Dark refined
BG_BASE = "#1d2021"          # Deep warm charcoal background
BG_SURFACE = "#282828"       # Container / Card surface
BG_OVERLAY = "#32302f"       # Elevated / Popup background
BG_HOVER = "#3c3836"         # Hover state
BG_BORDER = "#504945"        # Subtle borders
BG_BORDER_FOCUS = "#fe8019"  # Focused border (Amber)

FG_PRIMARY = "#ebdbb2"       # Warm cream primary text
FG_MUTED = "#a89984"         # Secondary muted text
FG_FAINT = "#7c6f64"         # Dim / placeholder text

# Functional Accents
ACCENT_WARM = "#fe8019"      # Amber orange (Primary accent)
ACCENT_SOFT = "#d3869b"      # Soft rose / purple (Secondary accent)
ACCENT_ROSE = ACCENT_SOFT
COLOR_SUCCESS = "#b8bb26"    # Sage green (Success / Tools)
COLOR_INFO = "#83a598"       # Soft blue (Information / Thinking)
COLOR_WARNING = "#fabd2f"    # Warm yellow (Warning)
COLOR_DANGER = "#fb4934"     # Coral red (Danger / Errors)

# Backward-compatibility aliases
BACKGROUND = BG_BASE
FOREGROUND = FG_PRIMARY
ACCENT = ACCENT_WARM
MUTED = FG_MUTED
