"""
Model Context Protocol (MCP) tools implementation.

This module provides MCP tool implementations that can work with any
graph operations backend (local or remote).
"""

from .tools import MCPTools, ToolResult

__all__ = ['MCPTools', 'ToolResult']
