"""The house domain (ADR-012 §2).

The vocabulary the engine used to hold as SQLEnum columns and as hard-coded
endpoint rules in EntityRelationship.is_valid_for_entities.
"""

from .manifest import HOUSE

__all__ = ["HOUSE"]
