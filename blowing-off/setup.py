"""
Blowing-Off Client - Package Setup Configuration

DEVELOPMENT CONTEXT:
Created as the package configuration in July 2025. This setup file defines
how the Blowing-Off client is packaged and installed. It specifies all runtime
dependencies and entry points for the CLI. This configuration serves as a
reference for the dependencies needed by any client implementing the Inbetweenies
protocol.

FUNCTIONALITY:
- Defines package metadata and version
- Specifies runtime dependencies with versions
- Configures CLI entry point for easy access
- Sets Python version requirements
- Enables pip-based installation
- Supports development mode installation

PURPOSE:
This setup enables:
- Easy installation via pip
- Dependency management and resolution
- CLI command registration
- Version tracking for releases
- Development workflow support
- Distribution preparation

KNOWN ISSUES:
- No optional dependencies defined yet
- Missing long description for PyPI
- No test dependencies specified
- Development dependencies not separated

REVISION HISTORY:
- 2025-07-28: Initial package configuration
- 2025-07-28: Added httpx for async HTTP
- 2025-07-28: Added tabulate for CLI output
- 2025-07-28: Updated SQLAlchemy to 2.0+

DEPENDENCIES:
- sqlalchemy: Async ORM for local database
- aiosqlite: SQLite async driver
- httpx: Async HTTP client for API calls
- click: CLI framework
- tabulate: Table formatting for output

USAGE:
    # Install in development mode
    pip install -e .

    # Install from package
    pip install blowing-off

    # Run CLI after installation
    blowing-off --help
"""

from setuptools import setup, find_packages

setup(
    name="blowingoff",
    version="0.1.0",
    description="Python test client for The Goodies smart home system",
    packages=find_packages(),
    install_requires=[
        "inbetweenies",
        "sqlalchemy>=2.0.0",
        "greenlet>=2.0.0",
        "aiosqlite>=0.17.0",
        "httpx>=0.24.0",
        "aiohttp>=3.8.0",
        "rich>=10.0.0",
        "click>=8.0.0",
        "tabulate>=0.9.0",
    ],
    entry_points={
        "console_scripts": [
            "blowing-off=blowingoff.cli.main:cli",
        ],
    },
    python_requires=">=3.11",
)
