#!/usr/bin/env python3
"""
FunkyGibbon Quick Start Script

DEVELOPMENT CONTEXT:
Simple startup script for human testing with pre-populated database.
Provides different startup modes for various testing scenarios.

FUNCTIONALITY:
- Quick start with populated database
- Different data scenarios (minimal, comprehensive)
- Automatic server startup after seeding
- Development-friendly logging and output

PURPOSE:
Enables quick setup for manual testing, demonstrations, and development
without requiring knowledge of CLI arguments or database setup.

REVISION HISTORY:
- 2025-07-29: Initial implementation for human testing setup
"""

import asyncio
import sys
import time
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from seed_data import seed_database, clear_database
from cli import handle_serve
import argparse


class QuickStart:
    """Quick start manager for FunkyGibbon."""
    
    def __init__(self):
        self.scenarios = {
            'minimal': {
                'name': 'Minimal Test Setup',
                'description': 'Single house with basic devices (3 rooms, 3 devices)',
                'houses': 1,
                'rooms': 3,
                'devices': 3,
                'users': 1
            },
            'comprehensive': {
                'name': 'Comprehensive Smart Home',
                'description': 'Multiple realistic scenarios (3 houses, full device ecosystem)',
                'houses': 3,
                'rooms': '10+',
                'devices': '25+',
                'users': '8+'
            }
        }
    
    def show_welcome(self):
        """Show welcome message and options."""
        print("\n" + "="*60)
        print("🏠 FunkyGibbon - Smart Home API Server")
        print("   Quick Start for Human Testing")
        print("="*60)
        print("\nAvailable scenarios:")
        print()
        
        for key, scenario in self.scenarios.items():
            print(f"  📋 {key.upper()}: {scenario['name']}")
            print(f"     {scenario['description']}")
            print(f"     • Houses: {scenario['houses']}")
            print(f"     • Rooms: {scenario['rooms']}")
            print(f"     • Devices: {scenario['devices']}")
            print(f"     • Users: {scenario['users']}")
            print()
    
    def get_user_choice(self):
        """Get user's choice for scenario."""
        while True:
            choice = input("Choose scenario (minimal/comprehensive) or 'q' to quit: ").lower().strip()
            
            if choice == 'q':
                print("👋 Goodbye!")
                sys.exit(0)
            elif choice in self.scenarios:
                return choice
            elif choice in ['m', 'min']:
                return 'minimal'
            elif choice in ['c', 'comp']:
                return 'comprehensive'
            else:
                print("❌ Invalid choice. Please enter 'minimal', 'comprehensive', or 'q'")
    
    async def setup_and_start(self, scenario):
        """Set up database and start server."""
        print(f"\n🚀 Starting {self.scenarios[scenario]['name']}...")
        print("="*50)
        
        # Step 1: Clear existing data
        print("\n1️⃣ Clearing existing database data...")
        try:
            await clear_database()
            print("   ✅ Database cleared")
        except Exception as e:
            print(f"   ⚠️  Warning: Could not clear database: {e}")
        
        # Step 2: Seed with new data
        print(f"\n2️⃣ Creating {scenario} test data...")
        try:
            counts = await seed_database(scenario)
            print("   ✅ Database populated successfully!")
            print(f"   📊 Created: {counts}")
        except Exception as e:
            print(f"   ❌ Error seeding database: {e}")
            return False
        
        # Step 3: Show what was created
        print(f"\n3️⃣ Ready for testing!")
        self.show_test_info(scenario, counts)
        
        # Step 4: Start server
        print("\n4️⃣ Starting API server...")
        return True
    
    def show_test_info(self, scenario, counts):
        """Show information about the test setup."""
        print("   🏠 Test Environment Ready:")
        
        if scenario == 'minimal':
            print("   • 1 house: 'Test Smart Home'")
            print("   • 3 rooms: Living Room, Kitchen, Bedroom")
            print("   • 3 devices: Basic lighting setup")
            print("   • 1 user: Test User (admin)")
        else:
            print("   • 3 houses: Smart Home, Apartment, Office")
            print("   • Multiple rooms with realistic layouts")
            print("   • Comprehensive device ecosystem")
            print("   • Multiple users with different roles")
        
        print(f"\n   📊 Database contains:")
        for entity_type, count in counts.items():
            print(f"   • {entity_type.capitalize()}: {count}")
        
        print(f"\n   🔗 API Endpoints available at:")
        print(f"   • Swagger UI: http://localhost:8000/docs")
        print(f"   • ReDoc: http://localhost:8000/redoc") 
        print(f"   • Health Check: http://localhost:8000/health")
        
        print(f"\n   🧪 Try these API calls:")
        print(f"   • GET  /api/v1/houses - List all houses")
        print(f"   • GET  /api/v1/rooms - List all rooms")
        print(f"   • GET  /api/v1/devices - List all devices")
        print(f"   • POST /api/v1/sync - Test sync functionality")


async def main():
    """Main entry point."""
    quick_start = QuickStart()
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        scenario = sys.argv[1].lower()
        if scenario not in quick_start.scenarios:
            print(f"❌ Invalid scenario: {scenario}")
            print(f"Available scenarios: {', '.join(quick_start.scenarios.keys())}")
            sys.exit(1)
    else:
        # Interactive mode
        quick_start.show_welcome()
        scenario = quick_start.get_user_choice()
    
    # Set up database and start server
    success = await quick_start.setup_and_start(scenario)
    
    if not success:
        print("\n❌ Setup failed. Please check the error messages above.")
        sys.exit(1)
    
    # Start the server
    print("\n" + "="*50)
    print("🌟 Setup complete! Starting server...")
    print("Press Ctrl+C to stop the server")
    print("="*50)
    
    # Small delay to let user read the info
    time.sleep(2)
    
    # Create args object for handle_serve
    class ServerArgs:
        host = 'localhost'
        port = 8000
        reload = True
        with_data = False  # Data already seeded
        scenario = scenario
    
    args = ServerArgs()
    
    try:
        await handle_serve(args)
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Thanks for testing FunkyGibbon!")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("🏠 FunkyGibbon Quick Start")
    asyncio.run(main())