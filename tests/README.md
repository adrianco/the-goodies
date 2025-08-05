# Integration and E2E Tests

This directory contains integration and end-to-end tests for The Goodies smart home system.

## Test Categories

### Security Tests (`auth/`)
- `test_audit_logger.py` - Tests for audit logging system
- `test_rate_limiter.py` - Tests for rate limiting functionality

### End-to-End Tests
- `test_e2e_with_security.py` - Complete flow with authentication enabled
- `test_multi_client_e2e.py` - Multi-client synchronization tests
- `test_security_penetration.py` - Security penetration and vulnerability tests

### Synchronization Tests
- `test_sync_simple.py` - Basic sync verification
- `test_sync_metadata.py` - Sync metadata handling
- `test_sync_metadata_api.py` - API-level sync tests
- `test_shared_sync_metadata.py` - Shared sync functionality

### Functionality Tests
- `test_graph_ops.py` - Graph operations testing
- `test_shared_mcp.py` - MCP tool functionality tests

## Running Tests

Make sure PYTHONPATH is set correctly:
```bash
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH
```

Run all tests:
```bash
python -m pytest tests/ -v
```

Run specific test category:
```bash
python -m pytest tests/auth/ -v        # Security tests only
python -m pytest tests/test_e2e* -v    # E2E tests only
```

## Note
These are integration tests that may require a running server or create temporary databases. Unit tests for individual components are located within their respective project directories (funkygibbon/tests, blowing-off/tests, etc.).