# Archived Plans

This directory contains obsolete planning documents from the original enterprise-scale design of The Goodies system. These documents have been superseded by the simplified single-house approach but are kept for historical reference.

## Contents

- **homegraph_analysis_summary.md** - Original analysis of the home graph concept
- **homegraph_mcp_library_initial_plan.md** - Initial ambitious plan for MCP library
- **test-execution-plan.md** - Original comprehensive test execution plan
- **testing-strategy.md** - Original testing strategy for distributed system

## Why Archived?

The original plans assumed:
- Multiple houses with distributed synchronization
- Complex vector clock conflict resolution
- WebSocket real-time updates
- PostgreSQL + Redis architecture
- MCP server implementation
- 12-week timeline

The current simplified approach focuses on:
- Single house deployment
- SQLite-only storage
- Last-write-wins conflict resolution
- REST API only
- 4-week timeline
- ~300 entities maximum

See the [simplified requirements](../simplified-requirements.md) for the current scope.