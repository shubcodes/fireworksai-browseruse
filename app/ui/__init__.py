"""
OpenManus UI module for web-based interaction with the agent.

This module provides a web UI with a split-screen layout:
- Left side: Chat interface for interacting with the agent
- Right side: Agent activity log and browser view (when active)
"""

from app.ui.server import OpenManusUI

__all__ = ["OpenManusUI"]
