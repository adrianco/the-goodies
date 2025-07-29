"""
Blowing-Off Client - Package Root Module

DEVELOPMENT CONTEXT:
Created as the package entry point in January 2024. This module exports the
public API of the Blowing-Off client, providing clean access to the main
components needed by applications. It follows Python best practices for
package organization and serves as the reference API that the Swift/WildThing
client should mirror.

FUNCTIONALITY:
- Exports main BlowingOffClient class for application use
- Provides access to sync state management objects
- Defines package version for compatibility tracking
- Controls public API surface through __all__
- Enables clean imports for client applications

PURPOSE:
This module ensures:
- Clean public API definition
- Version tracking for compatibility
- Controlled exports for stability
- Easy imports for applications
- Clear documentation entry point

KNOWN ISSUES:
- Limited public API exports (intentional for now)
- No deprecation warnings for future changes
- Missing API stability markers

REVISION HISTORY:
- 2024-01-15: Initial package structure
- 2024-01-18: Added sync state exports
- 2024-01-20: Refined public API surface

DEPENDENCIES:
- Internal modules only
- No external dependencies at package level

USAGE:
    from blowingoff import BlowingOffClient, SyncResult
    
    # Create and use client
    client = BlowingOffClient()
    await client.connect(server_url, auth_token)
    result = await client.sync()
"""

__version__ = "0.1.0"

from .client import BlowingOffClient
from .sync.state import SyncState, SyncResult
from .models.base import SyncStatus

__all__ = ["BlowingOffClient", "SyncState", "SyncResult", "SyncStatus"]