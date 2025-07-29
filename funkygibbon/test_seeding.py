#!/usr/bin/env python3
"""
Simple test script to verify seeding works correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Add parent directory for proper imports
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

async def test_basic_seeding():
    """Test that we can at least create a house using the repository."""
    print("🧪 Testing basic database seeding functionality...")
    
    try:
        # Import from the parent package
        from funkygibbon.repositories import HouseRepository
        from funkygibbon.database import get_async_session
        
        print("✅ Imports successful")
        
        # Create a test house
        async with get_async_session() as session:
            house_repo = HouseRepository()
            house = await house_repo.create(
                session,
                name="Test Seeding House",
                address="123 Test St"
            )
            print(f"✅ Created test house: {house.name} (ID: {house.id})")
            return True
            
    except Exception as e:
        print(f"❌ Error during basic seeding test: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_basic_seeding())
    if result:
        print("\n🎉 Basic seeding functionality works!")
        print("The full seeding system should work when run through the proper startup scripts.")
    else:
        print("\n❌ Basic seeding test failed")
    
    sys.exit(0 if result else 1)