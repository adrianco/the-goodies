"""Setup for Inbetweenies shared models package."""

from setuptools import setup, find_packages

setup(
    name="inbetweenies",
    version="0.1.0",
    description="Shared models for the Inbetweenies sync protocol",
    packages=find_packages(),
    install_requires=[
        "sqlalchemy>=2.0.0",
    ],
    python_requires=">=3.8",
)