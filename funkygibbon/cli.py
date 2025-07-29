#!/usr/bin/env python3
"""
FunkyGibbon CLI - Database Management and Development Tools

DEVELOPMENT CONTEXT:
Command-line interface for FunkyGibbon development and testing operations.
Provides easy access to database seeding, server management, and testing utilities.

FUNCTIONALITY:
- Database seeding with realistic test data
- Server startup with different configurations
- Development utilities and shortcuts
- Testing data management

PURPOSE:
Streamlines development workflow by providing common operations through
a simple command-line interface.

REVISION HISTORY:
- 2025-07-29: Initial implementation with database seeding and server management
"""

import argparse
import asyncio
import sys
import subprocess
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from seed_data import seed_database, clear_database
from config import Settings


def create_parser():
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="FunkyGibbon Development CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Seed database with comprehensive test data
  python cli.py seed --scenario comprehensive
  
  # Start server with populated database
  python cli.py serve --with-data
  
  # Clear all database data
  python cli.py clear-db
  
  # Run server with minimal test data
  python cli.py serve --scenario minimal
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Seed command
    seed_parser = subparsers.add_parser('seed', help='Seed database with test data')
    seed_parser.add_argument(
        '--scenario', 
        choices=['minimal', 'comprehensive'],
        default='comprehensive',
        help='Data scenario to create (default: comprehensive)'
    )
    seed_parser.add_argument(
        '--clear-first',
        action='store_true',
        help='Clear existing data before seeding'
    )
    
    # Serve command
    serve_parser = subparsers.add_parser('serve', help='Start the FunkyGibbon server')
    serve_parser.add_argument(
        '--with-data',
        action='store_true',
        help='Seed database before starting server'
    )
    serve_parser.add_argument(
        '--scenario',
        choices=['minimal', 'comprehensive'],
        default='comprehensive',
        help='Data scenario when using --with-data'
    )
    serve_parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port to run server on (default: 8000)'
    )
    serve_parser.add_argument(
        '--host',
        default='localhost',
        help='Host to bind to (default: localhost)'
    )
    serve_parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload for development'
    )
    
    # Clear database command
    clear_parser = subparsers.add_parser('clear-db', help='Clear all database data')
    clear_parser.add_argument(
        '--confirm',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Run tests with optional data setup')
    test_parser.add_argument(
        '--with-data',
        action='store_true',
        help='Seed database before running tests'
    )
    test_parser.add_argument(
        '--scenario',
        choices=['minimal', 'comprehensive'],
        default='minimal',
        help='Data scenario when using --with-data'
    )
    test_parser.add_argument(
        'test_args',
        nargs='*',
        help='Additional arguments to pass to pytest'
    )
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show system information')
    
    return parser


async def handle_seed(args):
    """Handle the seed command."""
    print(f"🌱 Seeding database with '{args.scenario}' scenario...")
    
    if args.clear_first:
        print("🗑️ Clearing existing data first...")
        await clear_database()
    
    counts = await seed_database(args.scenario)
    
    print("\n✅ Database seeding completed!")
    print("🔗 You can now:")
    print(f"   • Start the server: python cli.py serve")
    print(f"   • Run tests: python cli.py test")
    print(f"   • View API docs: http://localhost:8000/docs")


async def handle_serve(args):
    """Handle the serve command."""
    if args.with_data:
        print(f"🌱 Seeding database with '{args.scenario}' scenario...")
        await seed_database(args.scenario)
        print("✅ Database seeding completed!\n")
    
    print(f"🚀 Starting FunkyGibbon server on {args.host}:{args.port}")
    print(f"📚 API Documentation: http://{args.host}:{args.port}/docs")
    print(f"🔄 Auto-reload: {'enabled' if args.reload else 'disabled'}")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Start the server using uvicorn
    cmd = [
        sys.executable, "-m", "uvicorn",
        "funkygibbon.main:app",
        "--host", args.host,
        "--port", str(args.port)
    ]
    
    if args.reload:
        cmd.append("--reload")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 Server stopped")


async def handle_clear_db(args):
    """Handle the clear-db command."""
    if not args.confirm:
        response = input("⚠️  This will delete ALL data from the database. Continue? (y/N): ")
        if response.lower() != 'y':
            print("❌ Cancelled")
            return
    
    print("🗑️ Clearing database...")
    await clear_database()
    print("✅ Database cleared")


def handle_test(args):
    """Handle the test command."""
    if args.with_data:
        print(f"🌱 Seeding database with '{args.scenario}' scenario...")
        asyncio.run(seed_database(args.scenario))
        print("✅ Database seeding completed!\n")
    
    print("🧪 Running tests...")
    
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Add any additional arguments
    if args.test_args:
        cmd.extend(args.test_args)
    else:
        # Default test arguments
        cmd.extend(["-v", "--tb=short"])
    
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted")
        sys.exit(1)


def handle_info(args):
    """Handle the info command."""
    settings = Settings()
    
    print("📋 FunkyGibbon System Information")
    print("=" * 40)
    print(f"🔧 Environment: {settings.environment}")
    print(f"🗄️ Database URL: {settings.database_url}")
    print(f"🌍 API Host: {settings.api_host}")
    print(f"🔌 API Port: {settings.api_port}")
    print(f"🐞 Debug Mode: {settings.debug}")
    print(f"📝 Log Level: {settings.log_level}")
    
    # Check if database file exists (for SQLite)
    if "sqlite" in settings.database_url:
        db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
        if db_path != ":memory:":
            db_file = Path(db_path)
            if db_file.exists():
                size_mb = db_file.stat().st_size / (1024 * 1024)
                print(f"💾 Database File: {db_file} ({size_mb:.2f} MB)")
            else:
                print(f"💾 Database File: {db_file} (not found)")
    
    print("\n🚀 Quick Start Commands:")
    print("  python cli.py seed              # Populate with test data")
    print("  python cli.py serve --with-data # Start server with data")
    print("  python cli.py test              # Run test suite")


async def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'seed':
            await handle_seed(args)
        elif args.command == 'serve':
            await handle_serve(args)
        elif args.command == 'clear-db':
            await handle_clear_db(args)
        elif args.command == 'test':
            handle_test(args)
        elif args.command == 'info':
            handle_info(args)
        else:
            print(f"❌ Unknown command: {args.command}")
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.command in ['seed', 'serve', 'clear-db']:
            print("💡 Make sure the database is accessible and properly configured")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())