"""Setup for Inbetweenies shared models package.

PACKAGING NOTE:
This directory *is* the ``inbetweenies`` package root -- the modules live
directly here (``models/``, ``mcp/``, ``sync/``, ``graph/``, ...) rather than in
a nested ``inbetweenies/inbetweenies/`` source directory like the sibling
``oook`` and ``blowing-off`` projects.

A bare ``find_packages()`` therefore discovers those subdirectories as
*top level* distributions named ``models``, ``mcp``, ``sync`` and ``graph``.
Because CI and install.sh install this project with ``cd inbetweenies && pip
install -e .``, that made ``import mcp`` resolve to ``inbetweenies/mcp/``
instead of the real third-party MCP SDK.

The fix is to declare a single top-level package, ``inbetweenies``, rooted at
this directory, with everything else registered as a subpackage of it.
``pyproject.toml`` sits alongside this file so that pip uses the PEP 517/660
build path; the resulting editable install maps the name ``inbetweenies`` to
this directory via an import finder instead of dropping the directory itself
onto ``sys.path``.
"""

import os

from setuptools import setup, find_packages

HERE = os.path.dirname(os.path.abspath(__file__))

# Subpackages are discovered relative to this directory and then re-parented
# under the single ``inbetweenies`` top-level package.
SUBPACKAGES = find_packages(where=HERE, exclude=["tests", "tests.*"])

setup(
    name="inbetweenies",
    version="0.2.0",
    description="Shared models for the Inbetweenies sync protocol",
    packages=["inbetweenies"] + [f"inbetweenies.{name}" for name in SUBPACKAGES],
    package_dir={"inbetweenies": "."},
    install_requires=[
        "sqlalchemy>=2.0.0",
    ],
    python_requires=">=3.8",
)
