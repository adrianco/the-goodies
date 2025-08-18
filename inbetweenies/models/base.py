"""
Inbetweenies Protocol - Shared Base Models (HomeKit Compatible)

DEVELOPMENT CONTEXT:
Created in July 2025 as the foundation for shared models between FunkyGibbon
server and all client implementations. These models are designed to match
HomeKit's structure for seamless integration with iOS/macOS clients using
the HomeKit framework.

FUNCTIONALITY:
- Base declarative class for all SQLAlchemy models
- InbetweeniesTimestampMixin for sync tracking
- HomeKit-compatible field structure
- UTC timestamp handling with timezone awareness
- Sync ID for conflict resolution

HOMEKIT STRUCTURE:
- Home: The top-level container (was House)
- Room: Locations within a home
- Accessory: Physical devices (was Device)
- Service: Functions an accessory provides (e.g., light, thermostat)
- Characteristic: Properties of a service (e.g., on/off, brightness)
- User: Home members with permissions

PURPOSE:
Provides a common data model that works across all components of the system
while maintaining compatibility with Apple's HomeKit framework. This enables
native iOS/macOS integration without translation layers.

KNOWN ISSUES:
- No soft delete support (not in HomeKit)
- No version tracking (not in HomeKit)
- Limited to HomeKit's data model constraints

REVISION HISTORY:
- 2025-07-28: Initial shared model design
- 2025-07-29: Confirmed HomeKit field mapping
- 2025-07-29: Removed non-HomeKit fields

DEPENDENCIES:
- sqlalchemy: ORM framework
- datetime: UTC timestamp handling
"""

from datetime import datetime, UTC
from typing import Optional
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Float
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class InbetweeniesTimestampMixin:
    """Minimal sync tracking for HomeKit compatibility."""

    @declared_attr
    def created_at(cls):
        return Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    @declared_attr
    def updated_at(cls):
        return Column(DateTime, nullable=False, default=lambda: datetime.now(UTC),
                     onupdate=lambda: datetime.now(UTC))

    @declared_attr
    def sync_id(cls):
        """Unique identifier for sync operations."""
        return Column(String(36), nullable=True)  # UUID format
