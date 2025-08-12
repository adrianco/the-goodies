#!/bin/bash
# Run all tests for the blowing-off client

echo "================================"
echo "Running Blowing-Off Client Tests"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to script directory
cd "$(dirname "$0")"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed${NC}"
    echo "Please install it with: pip install pytest pytest-asyncio pytest-cov"
    exit 1
fi

# Run unit tests
echo -e "${YELLOW}Running Unit Tests...${NC}"
echo "------------------------"
pytest tests/unit/ -v --tb=short

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
else
    echo -e "${RED}✗ Unit tests failed${NC}"
fi
echo ""

# Run integration tests  
echo -e "${YELLOW}Running Integration Tests...${NC}"
echo "----------------------------"
pytest tests/integration/ -v --tb=short

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Integration tests passed${NC}"
else
    echo -e "${RED}✗ Integration tests failed${NC}"
fi
echo ""

# Run all tests with coverage
echo -e "${YELLOW}Running All Tests with Coverage...${NC}"
echo "-----------------------------------"
pytest tests/ --cov=blowingoff --cov-report=term-missing --cov-report=html

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All tests completed${NC}"
    echo "Coverage report generated in htmlcov/index.html"
else
    echo ""
    echo -e "${RED}✗ Some tests failed${NC}"
fi

echo ""
echo "================================"
echo "Test Summary"
echo "================================"

# Count test files
UNIT_TESTS=$(find tests/unit -name "test_*.py" | wc -l)
INTEGRATION_TESTS=$(find tests/integration -name "test_*.py" | wc -l)
TOTAL_TESTS=$((UNIT_TESTS + INTEGRATION_TESTS))

echo "Test files found:"
echo "  Unit tests: $UNIT_TESTS"
echo "  Integration tests: $INTEGRATION_TESTS"
echo "  Total: $TOTAL_TESTS"
echo ""

# Show test statistics
echo "To run specific test categories:"
echo "  Unit tests only:        pytest tests/unit/"
echo "  Integration tests only: pytest tests/integration/"
echo "  Specific test file:     pytest tests/unit/test_local_graph_storage.py"
echo "  With verbose output:    pytest -v"
echo "  With coverage:          pytest --cov=blowingoff"
echo ""