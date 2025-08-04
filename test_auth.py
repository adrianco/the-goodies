#!/usr/bin/env python3
"""
Test authentication system for The Goodies smart home.

Tests admin password login and guest QR code generation.
"""

import asyncio
import json
from pathlib import Path

# Test with in-process server for simplicity
from funkygibbon.auth import PasswordManager, TokenManager, QRCodeManager
import sys
sys.path.insert(0, 'blowing-off')
from blowingoff.auth import AuthManager


async def test_password_hashing():
    """Test password hashing and verification."""
    print("\n=== Testing Password Hashing ===")
    
    pm = PasswordManager()
    
    # Test password strength checking
    weak_password = "short"
    strong_password = "MySecure#Pass123!"
    
    is_strong, msg = pm.check_password_strength(weak_password)
    print(f"Weak password check: {msg}")
    assert not is_strong
    
    is_strong, msg = pm.check_password_strength(strong_password)
    print(f"Strong password check: {msg}")
    assert is_strong
    
    # Test hashing
    hash1 = pm.hash_password(strong_password)
    print(f"Password hash: {hash1[:50]}...")
    
    # Test verification
    is_valid, new_hash = pm.verify_password(strong_password, hash1)
    print(f"Password verification: {'✓' if is_valid else '✗'}")
    assert is_valid
    
    # Test wrong password
    is_valid, new_hash = pm.verify_password("wrong_password", hash1)
    print(f"Wrong password rejection: {'✓' if not is_valid else '✗'}")
    assert not is_valid
    
    print("Password hashing tests passed! ✓")


async def test_token_management():
    """Test JWT token creation and verification."""
    print("\n=== Testing Token Management ===")
    
    tm = TokenManager()
    
    # Create admin token
    admin_token = tm.create_token(
        user_id="admin",
        role="admin",
        permissions=["read", "write", "delete", "configure"]
    )
    print(f"Admin token created: {admin_token[:50]}...")
    
    # Verify token
    payload = tm.verify_token(admin_token)
    print(f"Token verified: role={payload['role']}, permissions={payload['permissions']}")
    assert payload['role'] == 'admin'
    
    # Create guest token
    guest_token = tm.create_guest_token(duration_hours=1)
    print(f"Guest token created: {guest_token[:20]}...")
    
    # Verify guest token
    token_data = tm.verify_guest_token(guest_token)
    print(f"Guest token verified: permissions={token_data['permissions']}")
    assert token_data['permissions'] == ['read']
    
    print("Token management tests passed! ✓")


async def test_qr_code_generation():
    """Test QR code generation."""
    print("\n=== Testing QR Code Generation ===")
    
    qr_manager = QRCodeManager()
    
    # Generate guest QR
    guest_token = "test_guest_token_12345"
    qr_data, qr_image = qr_manager.generate_guest_qr(
        guest_token=guest_token,
        duration_hours=24
    )
    
    print(f"QR data generated: server={qr_data['server']}, type={qr_data['type']}")
    print(f"QR image size: {len(qr_image)} characters (base64)")
    assert qr_data['type'] == 'guest_access'
    assert qr_data['token'] == guest_token
    
    # Parse QR data
    qr_string = json.dumps(qr_data)
    parsed = qr_manager.parse_qr_data(qr_string)
    print(f"QR data parsed: token={parsed['token'][:20]}...")
    assert parsed['token'] == guest_token
    
    print("QR code generation tests passed! ✓")


async def test_client_authentication():
    """Test client authentication flow."""
    print("\n=== Testing Client Authentication ===")
    
    # Create auth manager
    auth = AuthManager("http://localhost:8000")
    
    # Check initial state
    print(f"Initial auth state: authenticated={auth.is_authenticated()}")
    assert not auth.is_authenticated()
    
    # Simulate admin login (would normally connect to server)
    auth.token = "test_admin_token"
    auth.role = "admin"
    auth.permissions = ["read", "write", "delete", "configure"]
    from datetime import datetime, timedelta, timezone
    auth.token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    
    print(f"After login: authenticated={auth.is_authenticated()}, role={auth.role}")
    assert auth.is_authenticated()
    assert auth.role == "admin"
    
    # Check permissions
    print(f"Has read permission: {auth.has_permission('read')}")
    print(f"Has write permission: {auth.has_permission('write')}")
    print(f"Has delete permission: {auth.has_permission('delete')}")
    assert auth.has_permission('write')
    
    # Test logout
    auth.logout()
    print(f"After logout: authenticated={auth.is_authenticated()}")
    assert not auth.is_authenticated()
    
    print("Client authentication tests passed! ✓")


async def test_end_to_end_flow():
    """Test complete authentication flow."""
    print("\n=== Testing End-to-End Flow ===")
    
    # 1. Admin sets password during installation
    pm = PasswordManager()
    admin_password = "AdminSecure#2024!"
    admin_hash = pm.hash_password(admin_password)
    print(f"1. Admin password set and hashed")
    
    # 2. Create token manager with secret
    tm = TokenManager(secret_key="test_secret_key_12345")
    
    # 3. Admin logs in (simulate successful auth)
    is_valid, _ = pm.verify_password(admin_password, admin_hash)
    if is_valid:
        admin_token = tm.create_token(
            user_id="admin",
            role="admin",
            permissions=["read", "write", "delete", "configure"]
        )
        print(f"2. Admin logged in successfully")
    
    # 4. Admin generates guest QR
    guest_token = tm.create_guest_token(duration_hours=24)
    qr_manager = QRCodeManager()
    qr_data, qr_image = qr_manager.generate_guest_qr(
        guest_token=guest_token,
        duration_hours=24
    )
    print(f"3. Guest QR code generated")
    
    # 5. Guest scans QR (simulate)
    qr_string = json.dumps(qr_data)
    parsed_qr = qr_manager.parse_qr_data(qr_string)
    
    # 6. Guest verifies token
    guest_data = tm.verify_guest_token(parsed_qr['token'])
    if guest_data:
        guest_jwt = tm.create_token(
            user_id=f"guest_{parsed_qr['token'][:8]}",
            role="guest",
            permissions=guest_data['permissions']
        )
        print(f"4. Guest authenticated with read-only access")
    
    # 7. Verify both tokens work
    admin_payload = tm.verify_token(admin_token)
    guest_payload = tm.verify_token(guest_jwt)
    
    print(f"\nAdmin access: role={admin_payload['role']}, can_write={
'write' in admin_payload['permissions']}")
    print(f"Guest access: role={guest_payload['role']}, can_write={'write' in guest_payload['permissions']}")
    
    assert admin_payload['role'] == 'admin'
    assert 'write' in admin_payload['permissions']
    assert guest_payload['role'] == 'guest'
    assert 'write' not in guest_payload['permissions']
    
    print("\nEnd-to-end flow tests passed! ✓")


async def main():
    """Run all authentication tests."""
    print("=" * 50)
    print("Testing The Goodies Authentication System")
    print("=" * 50)
    
    try:
        await test_password_hashing()
        await test_token_management()
        await test_qr_code_generation()
        await test_client_authentication()
        await test_end_to_end_flow()
        
        print("\n" + "=" * 50)
        print("✅ All authentication tests passed!")
        print("=" * 50)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)