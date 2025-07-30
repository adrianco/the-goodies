"""
Setup script for Oook CLI
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="oook",
    version="0.1.0",
    author="The Goodies Team",
    description="CLI tool for testing FunkyGibbon MCP server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/thegoodies/oook",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=[
        "click>=8.0",
        "httpx>=0.24.0",
        "rich>=13.0",
    ],
    entry_points={
        "console_scripts": [
            "oook=oook.cli:cli",
        ],
    },
)