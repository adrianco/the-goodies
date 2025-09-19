"""
Pytest configuration for chat tests
===================================

Provides options to run tests with mock data or against real server.
"""

import pytest


def pytest_addoption(parser):
    """Add command-line options for test configuration"""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run tests against real FunkyGibbon server instead of mock data"
    )
    parser.addoption(
        "--server-url",
        action="store",
        default="http://localhost:8000",
        help="FunkyGibbon server URL for integration tests"
    )
    parser.addoption(
        "--server-password",
        action="store",
        default="admin",
        help="Admin password for FunkyGibbon server"
    )


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring real server (use --integration to run)"
    )
    config.addinivalue_line(
        "markers",
        "unit: mark test as unit test with mock data (default)"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on --integration flag"""
    if config.getoption("--integration"):
        # Running integration tests - skip unit tests
        skip_unit = pytest.mark.skip(reason="Running integration tests only")
        for item in items:
            if "unit" in item.keywords and "integration" not in item.keywords:
                item.add_marker(skip_unit)
    else:
        # Running unit tests - skip integration tests
        skip_integration = pytest.mark.skip(reason="Use --integration to run integration tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


@pytest.fixture(scope="session")
def integration_mode(request):
    """Check if running in integration mode"""
    return request.config.getoption("--integration")


@pytest.fixture(scope="session")
def server_config(request):
    """Get server configuration for integration tests"""
    return {
        "url": request.config.getoption("--server-url"),
        "password": request.config.getoption("--server-password")
    }