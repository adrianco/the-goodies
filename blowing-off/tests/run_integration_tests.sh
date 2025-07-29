#!/bin/bash

# Script to run integration tests with FunkyGibbon server

echo "🚀 Starting integration tests for Blowing-Off client"
echo "================================================"

# Check if server is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ FunkyGibbon server is not running!"
    echo "Please start it with: cd ../funkygibbon && python -m funkygibbon.main"
    exit 1
fi

echo "✅ FunkyGibbon server is running"

# Run integration tests
echo "🧪 Running integration tests..."
python -m pytest integration/ -v --tb=short

# Run with coverage if requested
if [ "$1" == "--coverage" ]; then
    echo "📊 Running with coverage..."
    python -m pytest integration/ --cov=blowing_off --cov-report=html --cov-report=term
fi

echo "✅ Integration tests complete!"