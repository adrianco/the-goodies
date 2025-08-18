"""
Blowing-Off Client - CLI Package

DEVELOPMENT CONTEXT:
Created as the command-line interface package in July 2025. This package
provides an interactive way to test and use the Blowing-Off client. It serves
as both a development tool and a reference implementation for how the client
API should be used in applications.

FUNCTIONALITY:
- Exports the main CLI entry point
- Provides command organization structure
- Enables pip-installed CLI commands
- Supports plugin-style command extensions

PURPOSE:
This package enables:
- Interactive client testing
- Debugging sync operations
- Demonstrating API usage
- Performance testing
- Quick setup validation

KNOWN ISSUES:
- Limited command set currently
- No shell completion support
- Missing batch operation commands

REVISION HISTORY:
- 2025-07-28: Initial CLI structure
- 2025-07-28: Added main command groups
- 2025-07-28: Exported cli entry point

DEPENDENCIES:
- click for CLI framework
- Main module with command implementations

USAGE:
    # After pip install
    blowingoff --help

    # Or programmatically
    from blowingoff.cli import cli
    cli()
"""

from .main import cli

__all__ = ["cli"]
