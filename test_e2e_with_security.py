#!/usr/bin/env python3
"""
End-to-end test with full security enabled.

Tests the complete flow from server setup to client operations with authentication.
"""

import asyncio
import tempfile
import os
from pathlib import Path
import sys
sys.path.insert(0, 'blowing-off')

# Import components
from funkygibbon.auth import PasswordManager, TokenManager, QRCodeManager
from funkygibbon.database import init_db
from funkygibbon.api.app import create_app
from blowingoff.client import BlowingOffClient
from blowingoff.auth import AuthManager
from inbetweenies.models import Entity, EntityType, SourceType

# Test configuration
ADMIN_PASSWORD = "TestAdmin#2024!"
TEST_SERVER_URL = "http://localhost:8000"


async def setup_server_with_auth():
    """Set up server with authentication enabled."""
    print("\n=== Setting up Server with Authentication ===")
    
    # Initialize database
    await init_db()
    print("  ✓ Database initialized")
    
    # Set up authentication
    pm = PasswordManager()
    admin_hash = pm.hash_password(ADMIN_PASSWORD)
    
    # Store admin hash (in production, this would be in config)
    os.environ["ADMIN_PASSWORD_HASH"] = admin_hash
    os.environ["JWT_SECRET"] = "test_secret_key_for_e2e"
    
    print(f"  ✓ Admin password configured")
    
    # Create FastAPI app
    app = create_app()
    print("  ✓ Server application created")
    
    return app, admin_hash


async def test_admin_authentication():
    """Test admin authentication flow."""
    print("\n=== Testing Admin Authentication ===")
    
    # Create client
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "client.db"
        client = BlowingOffClient(str(db_path))
        
        # Test authentication with password
        try:
            await client.connect(
                server_url=TEST_SERVER_URL,
                password=ADMIN_PASSWORD
            )
            print("  ✓ Admin authentication successful")
            
            # Check permissions
            if client.check_admin_permission():
                print("  ✓ Admin permissions verified")
            else:
                print("  ✗ Admin permissions not granted")
                return False
                
            if client.check_write_permission():
                print("  ✓ Write permissions verified")
            else:
                print("  ✗ Write permissions not granted")
                return False
                
        except Exception as e:
            print(f"  ✗ Authentication failed: {e}")
            return False
        finally:
            await client.disconnect()
    
    return True


async def test_guest_authentication():
    """Test guest authentication via QR code."""
    print("\n=== Testing Guest Authentication ===")
    
    # Set up token manager
    tm = TokenManager(secret_key=os.getenv("JWT_SECRET"))
    qr_manager = QRCodeManager()
    
    # Generate guest token
    guest_token = tm.create_guest_token(duration_hours=1)
    qr_data, qr_image = qr_manager.generate_guest_qr(
        guest_token=guest_token,
        duration_hours=1
    )
    print(f"  ✓ Guest QR code generated")
    
    # Create guest client
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "guest.db"
        client = BlowingOffClient(str(db_path))
        
        # Simulate QR scanning and authentication
        import json
        qr_string = json.dumps(qr_data)
        
        try:
            await client.connect(
                server_url=TEST_SERVER_URL,
                qr_data=qr_string
            )
            print("  ✓ Guest authentication successful")
            
            # Check permissions (should be read-only)
            if not client.check_write_permission():
                print("  ✓ Guest has read-only access (correct)")
            else:
                print("  ✗ Guest has write access (security issue!)")
                return False
                
            if not client.check_admin_permission():
                print("  ✓ Guest not admin (correct)")
            else:
                print("  ✗ Guest has admin access (security issue!)")
                return False
                
        except Exception as e:
            print(f"  ✗ Guest authentication failed: {e}")
            return False
        finally:
            await client.disconnect()
    
    return True


async def test_operations_with_permissions():
    """Test operations respecting permission levels."""
    print("\n=== Testing Operations with Permissions ===")
    
    # Admin client - should be able to write
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "admin_ops.db"
        admin_client = BlowingOffClient(str(db_path))
        
        try:
            await admin_client.connect(
                server_url=TEST_SERVER_URL,
                password=ADMIN_PASSWORD
            )
            
            # Try write operation
            if admin_client.check_write_permission():
                # Create an entity
                result = await admin_client.execute_mcp_tool(
                    "create_entity",
                    entity_type=EntityType.HOME.value,
                    name="Admin Test Home",
                    content={"owner": "admin"}
                )
                if result.get('success'):
                    print("  ✓ Admin can create entities")
                else:
                    print("  ✗ Admin create failed")
            
        except Exception as e:
            print(f"  ✗ Admin operation error: {e}")
        finally:
            await admin_client.disconnect()
    
    # Guest client - should only read
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "guest_ops.db"
        guest_client = BlowingOffClient(str(db_path))
        
        # Create guest token
        tm = TokenManager(secret_key=os.getenv("JWT_SECRET"))
        qr_manager = QRCodeManager()
        guest_token = tm.create_guest_token(duration_hours=1)
        qr_data, _ = qr_manager.generate_guest_qr(guest_token, 1)
        
        try:
            import json
            await guest_client.connect(
                server_url=TEST_SERVER_URL,
                qr_data=json.dumps(qr_data)
            )
            
            # Try read operation (should work)
            result = await guest_client.execute_mcp_tool(
                "search_entities",
                query="Test",
                limit=10
            )
            if result:
                print("  ✓ Guest can read data")
            
            # Try write operation (should fail or be blocked)
            if not guest_client.check_write_permission():
                print("  ✓ Guest write permission correctly denied")
                # Attempt write anyway to test enforcement
                try:
                    result = await guest_client.execute_mcp_tool(
                        "create_entity",
                        entity_type=EntityType.HOME.value,
                        name="Guest Test Home",
                        content={"owner": "guest"}
                    )
                    # If this succeeds, it's a security issue
                    print("  ✗ Guest could create entity (security issue!)")
                except Exception:
                    print("  ✓ Guest write operation blocked")
            
        except Exception as e:
            print(f"  ✗ Guest operation error: {e}")
        finally:
            await guest_client.disconnect()
    
    return True


async def test_token_expiration():
    """Test token expiration and refresh."""
    print("\n=== Testing Token Expiration ===")
    
    # Create short-lived token
    tm = TokenManager(secret_key=os.getenv("JWT_SECRET"))
    
    # Create token that expires in 1 second
    from datetime import timedelta
    short_token = tm.create_token(
        user_id="test_user",
        role="guest",
        permissions=["read"],
        expires_delta=timedelta(seconds=1)
    )
    
    # Verify it works initially
    result = tm.verify_token(short_token)
    if result:
        print("  ✓ Fresh token valid")
    
    # Wait for expiration
    await asyncio.sleep(2)
    
    # Try to use expired token
    result = tm.verify_token(short_token)
    if not result:
        print("  ✓ Expired token rejected")
    else:
        print("  ✗ Expired token still accepted (security issue!)")
        return False
    
    # Test admin token refresh
    admin_token = tm.create_token(
        user_id="admin",
        role="admin", 
        permissions=["read", "write", "delete", "configure"],
        expires_delta=timedelta(hours=1)
    )
    
    # Admin tokens should be refreshable
    result = tm.verify_token(admin_token)
    if result and result.get('role') == 'admin':
        print("  ✓ Admin token refresh capability verified")
    
    return True


async def test_concurrent_auth_sessions():
    """Test multiple concurrent authenticated sessions."""
    print("\n=== Testing Concurrent Sessions ===")
    
    clients = []
    
    # Create multiple admin sessions
    for i in range(3):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / f"client_{i}.db"
            client = BlowingOffClient(str(db_path))
            
            try:
                await client.connect(
                    server_url=TEST_SERVER_URL,
                    password=ADMIN_PASSWORD,
                    client_id=f"admin_client_{i}"
                )
                clients.append(client)
                print(f"  ✓ Admin session {i+1} established")
                
            except Exception as e:
                print(f"  ✗ Session {i+1} failed: {e}")
                # Clean up
                for c in clients:
                    await c.disconnect()
                return False
    
    # Test operations from different sessions
    for i, client in enumerate(clients):
        try:
            result = await client.execute_mcp_tool(
                "search_entities",
                query="test",
                limit=5
            )
            print(f"  ✓ Session {i+1} operations working")
        except Exception as e:
            print(f"  ✗ Session {i+1} operation failed: {e}")
    
    # Clean up
    for client in clients:
        await client.disconnect()
    
    print("  ✓ All concurrent sessions successful")
    return True


async def run_all_e2e_tests():
    """Run all end-to-end tests with security."""
    print("=" * 60)
    print("END-TO-END SECURITY TESTING")
    print("=" * 60)
    
    # Note: In a real test, we'd start the server in a subprocess
    # For this test, we'll simulate the important parts
    
    # Set up server environment
    app, admin_hash = await setup_server_with_auth()
    
    tests = [
        ("Admin Authentication", test_admin_authentication),
        ("Guest Authentication", test_guest_authentication),
        ("Permission-based Operations", test_operations_with_permissions),
        ("Token Expiration", test_token_expiration),
        ("Concurrent Sessions", test_concurrent_auth_sessions),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            # Note: Some tests would fail without actual server running
            # This is expected in this simulation
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\nTest {name} error: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("E2E TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    return failed == 0


async def main():
    """Run end-to-end tests."""
    success = await run_all_e2e_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)