"""The vehicles domain (ADR-012) -- the second domain, and the proof.

A manifest and nothing else. Serve it with
``DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES``.
"""

from .manifest import VEHICLES

__all__ = ["VEHICLES"]
