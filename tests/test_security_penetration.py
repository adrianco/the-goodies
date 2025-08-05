#!/usr/bin/env python3
"""
Security Penetration and Privilege Escalation Tests.

Tests for authentication bypass, privilege escalation, token manipulation,
and other security vulnerabilities.
"""

import asyncio
import json
import jwt
import base64
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import secrets
# Imports work with proper PYTHONPATH

from funkygibbon.auth import PasswordManager, TokenManager, QRCodeManager
from blowingoff.auth import AuthManager


class SecurityPenetrationTests:
    """Security penetration testing suite."""
    
    def __init__(self):
        self.pm = PasswordManager()
        self.tm = TokenManager(secret_key="test_secret_key")
        self.qr = QRCodeManager()
        self.results = []
        self.vulnerabilities = []
    
    async def test_privilege_escalation_guest_to_admin(self):
        """Test if guest can escalate privileges to admin."""
        print("\n=== Testing Privilege Escalation: Guest → Admin ===")
        
        # Create legitimate guest token
        guest_token = self.tm.create_guest_token(duration_hours=1)
        guest_jwt = self.tm.create_token(
            user_id=f"guest_{guest_token[:8]}",
            role="guest",
            permissions=["read"]
        )
        
        # Test 1: Try to modify guest JWT to add admin role
        try:
            # Decode without verification (what an attacker might try)
            header, payload, signature = guest_jwt.split('.')
            decoded_payload = json.loads(
                base64.urlsafe_b64decode(payload + '==')
            )
            
            # Attempt to escalate privileges
            decoded_payload['role'] = 'admin'
            decoded_payload['permissions'] = ['read', 'write', 'delete', 'configure']
            
            # Re-encode with modified payload
            modified_payload = base64.urlsafe_b64encode(
                json.dumps(decoded_payload).encode()
            ).rstrip(b'=').decode()
            
            # Create fake token with original signature (invalid)
            fake_token = f"{header}.{modified_payload}.{signature}"
            
            # Try to verify the modified token
            verified = self.tm.verify_token(fake_token)
            
            if verified and verified.get('role') == 'admin':
                self.vulnerabilities.append("CRITICAL: Guest can escalate to admin by modifying JWT!")
                print("  ❌ VULNERABLE: Token modification allowed privilege escalation")
            else:
                print("  ✅ SECURE: Modified token rejected")
                
        except Exception as e:
            print(f"  ✅ SECURE: Token manipulation failed - {type(e).__name__}")
        
        # Test 2: Try to use guest token to access admin endpoints
        print("\n  Testing endpoint access with guest token...")
        
        # Simulate checking permissions
        guest_payload = self.tm.verify_token(guest_jwt)
        if guest_payload:
            can_generate_qr = 'configure' in guest_payload.get('permissions', [])
            can_delete = 'delete' in guest_payload.get('permissions', [])
            can_write = 'write' in guest_payload.get('permissions', [])
            
            if any([can_generate_qr, can_delete, can_write]):
                self.vulnerabilities.append("CRITICAL: Guest has elevated permissions!")
                print(f"  ❌ VULNERABLE: Guest has permissions: {guest_payload.get('permissions')}")
            else:
                print(f"  ✅ SECURE: Guest limited to: {guest_payload.get('permissions')}")
        
        # Test 3: Try to create admin token using guest credentials
        print("\n  Testing token creation with guest credentials...")
        try:
            # Guest shouldn't be able to create admin tokens
            admin_attempt = self.tm.create_token(
                user_id="guest_escalated",
                role="admin",
                permissions=["read", "write", "delete", "configure"]
            )
            
            # This would work in our current implementation, but verification should fail
            # if proper role checking is in place at the endpoint level
            print("  ⚠️  WARNING: Token creation not role-restricted (endpoint validation required)")
            
        except Exception as e:
            print(f"  ✅ SECURE: Admin token creation blocked - {e}")
        
        return len(self.vulnerabilities) == 0
    
    async def test_authentication_bypass(self):
        """Test various authentication bypass techniques."""
        print("\n=== Testing Authentication Bypass Attempts ===")
        
        # Test 1: Empty/None token
        print("\n  Testing empty/null tokens...")
        for invalid_token in [None, "", " ", "null", "undefined"]:
            result = self.tm.verify_token(invalid_token) if invalid_token else None
            if result:
                self.vulnerabilities.append(f"CRITICAL: Empty/null token '{invalid_token}' accepted!")
                print(f"  ❌ VULNERABLE: Token '{invalid_token}' accepted")
            else:
                print(f"  ✅ SECURE: Token '{invalid_token}' rejected")
        
        # Test 2: Malformed tokens
        print("\n  Testing malformed tokens...")
        malformed_tokens = [
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Missing parts
            "not.a.token",  # Invalid format
            "a.b.c.d.e",  # Too many parts
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiJ9.",  # Algorithm none
        ]
        
        for token in malformed_tokens:
            result = self.tm.verify_token(token)
            if result:
                self.vulnerabilities.append(f"CRITICAL: Malformed token accepted!")
                print(f"  ❌ VULNERABLE: Malformed token accepted")
            else:
                print(f"  ✅ SECURE: Malformed token rejected")
        
        # Test 3: SQL injection in password field
        print("\n  Testing SQL injection in password...")
        sql_injections = [
            "' OR '1'='1",
            "admin'--",
            "'; DROP TABLE users;--",
            "' UNION SELECT * FROM users--"
        ]
        
        # Create a test hash
        real_hash = self.pm.hash_password("RealPassword123!")
        
        for injection in sql_injections:
            try:
                valid, _ = self.pm.verify_password(injection, real_hash)
                if valid:
                    self.vulnerabilities.append(f"CRITICAL: SQL injection '{injection}' succeeded!")
                    print(f"  ❌ VULNERABLE: Injection '{injection}' accepted")
                else:
                    print(f"  ✅ SECURE: Injection '{injection}' rejected")
            except Exception:
                print(f"  ✅ SECURE: Injection '{injection}' caused safe error")
        
        # Test 4: Password timing attacks
        print("\n  Testing timing attack resistance...")
        import time
        
        real_hash = self.pm.hash_password("RealPassword123!")
        timings = []
        
        # Test with correct vs incorrect passwords
        passwords = ["RealPassword123!", "WrongPassword123!", "X", "X" * 100]
        
        for pwd in passwords:
            start = time.perf_counter()
            self.pm.verify_password(pwd, real_hash)
            elapsed = time.perf_counter() - start
            timings.append(elapsed)
        
        # Check if timing differences are significant (potential leak)
        time_variance = max(timings) - min(timings)
        if time_variance > 0.1:  # 100ms difference
            print(f"  ⚠️  WARNING: Large timing variance ({time_variance:.3f}s) - potential timing attack")
        else:
            print(f"  ✅ SECURE: Constant-time comparison (variance: {time_variance:.3f}s)")
        
        return len(self.vulnerabilities) == 0
    
    async def test_token_manipulation(self):
        """Test token manipulation and replay attacks."""
        print("\n=== Testing Token Manipulation ===")
        
        # Test 1: Algorithm confusion attack
        print("\n  Testing algorithm confusion...")
        
        # Create a valid token
        valid_token = self.tm.create_token("testuser", "guest", ["read"])
        
        # Try to change algorithm to 'none'
        try:
            header, payload, _ = valid_token.split('.')
            
            # Decode and modify header
            decoded_header = json.loads(
                base64.urlsafe_b64decode(header + '==')
            )
            decoded_header['alg'] = 'none'
            
            # Re-encode header
            new_header = base64.urlsafe_b64encode(
                json.dumps(decoded_header).encode()
            ).rstrip(b'=').decode()
            
            # Create token with no signature
            none_token = f"{new_header}.{payload}."
            
            result = self.tm.verify_token(none_token)
            if result:
                self.vulnerabilities.append("CRITICAL: Algorithm 'none' accepted!")
                print("  ❌ VULNERABLE: Algorithm confusion attack succeeded")
            else:
                print("  ✅ SECURE: Algorithm confusion attack blocked")
                
        except Exception:
            print("  ✅ SECURE: Algorithm manipulation failed")
        
        # Test 2: Expired token usage
        print("\n  Testing expired token rejection...")
        
        # Create token that expires immediately
        expired_token = self.tm.create_token(
            "testuser", "guest", ["read"],
            expires_delta=timedelta(seconds=-1)
        )
        
        result = self.tm.verify_token(expired_token)
        if result:
            self.vulnerabilities.append("CRITICAL: Expired token accepted!")
            print("  ❌ VULNERABLE: Expired token accepted")
        else:
            print("  ✅ SECURE: Expired token rejected")
        
        # Test 3: Token replay attack
        print("\n  Testing token replay protection...")
        
        # Create a valid token
        token1 = self.tm.create_token("user1", "guest", ["read"])
        
        # Verify it works initially
        result1 = self.tm.verify_token(token1)
        
        # Try to use it again (replay)
        result2 = self.tm.verify_token(token1)
        
        if result1 and result2:
            print("  ⚠️  WARNING: Token replay possible (implement nonce/jti for full protection)")
        else:
            print("  ✅ SECURE: Token replay protection active")
        
        # Test 4: Cross-tenant token usage
        print("\n  Testing cross-tenant token isolation...")
        
        # Create token with different secret
        other_tm = TokenManager(secret_key="different_secret")
        other_token = other_tm.create_token("attacker", "admin", ["read", "write"])
        
        # Try to verify with original token manager
        result = self.tm.verify_token(other_token)
        if result:
            self.vulnerabilities.append("CRITICAL: Cross-tenant token accepted!")
            print("  ❌ VULNERABLE: Token from different secret accepted")
        else:
            print("  ✅ SECURE: Cross-tenant token rejected")
        
        return len(self.vulnerabilities) == 0
    
    async def test_qr_code_security(self):
        """Test QR code security vulnerabilities."""
        print("\n=== Testing QR Code Security ===")
        
        # Test 1: QR code injection
        print("\n  Testing QR code data injection...")
        
        malicious_qr_data = [
            '{"type":"guest_access","token":"<script>alert(1)</script>"}',
            '{"type":"guest_access","server":"evil.com","token":"stolen"}',
            '{"type":"admin_access","token":"fake_admin"}',
        ]
        
        for data in malicious_qr_data:
            try:
                parsed = self.qr.parse_qr_data(data)
                if parsed.get('type') == 'admin_access':
                    self.vulnerabilities.append("CRITICAL: Admin access via QR code!")
                    print("  ❌ VULNERABLE: Admin QR code accepted")
                elif 'script' in str(parsed):
                    self.vulnerabilities.append("CRITICAL: XSS in QR code!")
                    print("  ❌ VULNERABLE: Script injection in QR")
                else:
                    print(f"  ⚠️  WARNING: Potentially malicious QR parsed")
            except ValueError:
                print("  ✅ SECURE: Malicious QR data rejected")
        
        # Test 2: QR code replay
        print("\n  Testing QR code replay attack...")
        
        # Generate a guest QR
        guest_token = self.tm.create_guest_token(duration_hours=1)
        qr_data, _ = self.qr.generate_guest_qr(guest_token, duration_hours=1)
        
        # First use
        token_data1 = self.tm.verify_guest_token(guest_token)
        
        # Try replay
        token_data2 = self.tm.verify_guest_token(guest_token)
        
        if token_data1 and token_data2:
            print("  ⚠️  WARNING: QR code replay possible (consider one-time use tokens)")
        else:
            print("  ✅ SECURE: QR code replay protection active")
        
        # Test 3: QR code expiration bypass
        print("\n  Testing QR expiration bypass...")
        
        # Create expired guest token
        expired_token = "expired_test_token"
        self.tm.guest_tokens[expired_token] = {
            "expires": datetime.now(timezone.utc) - timedelta(hours=1),
            "permissions": ["read"]
        }
        
        result = self.tm.verify_guest_token(expired_token)
        if result:
            self.vulnerabilities.append("CRITICAL: Expired QR token accepted!")
            print("  ❌ VULNERABLE: Expired QR token accepted")
        else:
            print("  ✅ SECURE: Expired QR token rejected")
        
        return len(self.vulnerabilities) == 0
    
    async def test_dos_and_rate_limiting(self):
        """Test denial of service and rate limiting."""
        print("\n=== Testing DOS Protection ===")
        
        # Test 1: Password brute force
        print("\n  Testing brute force protection...")
        
        real_hash = self.pm.hash_password("RealPassword123!")
        attempts = 0
        max_attempts = 100
        
        import time
        start_time = time.time()
        
        for i in range(max_attempts):
            try:
                self.pm.verify_password(f"wrong_{i}", real_hash)
                attempts += 1
            except Exception as e:
                if "rate limit" in str(e).lower():
                    print(f"  ✅ SECURE: Rate limiting activated after {attempts} attempts")
                    break
        
        elapsed = time.time() - start_time
        
        if attempts == max_attempts:
            print(f"  ⚠️  WARNING: No rate limiting detected ({attempts} attempts in {elapsed:.1f}s)")
            print("     Implement rate limiting to prevent brute force attacks")
        
        # Test 2: Token generation flooding
        print("\n  Testing token generation flooding...")
        
        tokens_created = 0
        try:
            for i in range(1000):
                self.tm.create_guest_token()
                tokens_created += 1
        except Exception as e:
            print(f"  ✅ SECURE: Token generation limited after {tokens_created} tokens")
        
        if tokens_created == 1000:
            print(f"  ⚠️  WARNING: Unlimited token generation (potential memory exhaustion)")
        
        # Test 3: Large payload attacks
        print("\n  Testing large payload handling...")
        
        large_payloads = [
            "A" * 10000,  # 10KB
            "B" * 100000,  # 100KB
            "C" * 1000000,  # 1MB
        ]
        
        for i, payload in enumerate(large_payloads):
            try:
                # Try to hash extremely long password
                self.pm.hash_password(payload)
                print(f"  ⚠️  WARNING: {len(payload)} byte password accepted")
            except Exception:
                print(f"  ✅ SECURE: Large payload ({len(payload)} bytes) rejected")
        
        return True
    
    async def test_cryptographic_weaknesses(self):
        """Test for cryptographic vulnerabilities."""
        print("\n=== Testing Cryptographic Security ===")
        
        # Test 1: Weak secret detection
        print("\n  Testing secret key strength...")
        
        weak_secrets = ["", "secret", "12345", "password"]
        
        for secret in weak_secrets:
            try:
                weak_tm = TokenManager(secret_key=secret)
                token = weak_tm.create_token("test", "admin", ["all"])
                
                # Try to crack with known weak secret
                for guess in weak_secrets:
                    guess_tm = TokenManager(secret_key=guess)
                    if guess_tm.verify_token(token):
                        if guess == secret:
                            print(f"  ⚠️  WARNING: Weak secret '{secret}' in use")
                        else:
                            self.vulnerabilities.append(f"CRITICAL: Token cracked with '{guess}'!")
                            print(f"  ❌ VULNERABLE: Weak secret cracked")
                        break
                        
            except Exception:
                print(f"  ✅ SECURE: Weak secret '{secret}' rejected")
        
        # Test 2: Salt uniqueness
        print("\n  Testing password salt uniqueness...")
        
        password = "TestPassword123!"
        hash1 = self.pm.hash_password(password)
        hash2 = self.pm.hash_password(password)
        
        if hash1 == hash2:
            self.vulnerabilities.append("CRITICAL: Password hashes not salted!")
            print("  ❌ VULNERABLE: Same password produces same hash")
        else:
            print("  ✅ SECURE: Unique salts for each hash")
        
        # Test 3: Hash algorithm strength
        print("\n  Testing hash algorithm...")
        
        if "$argon2" in hash1:
            print("  ✅ SECURE: Using Argon2 (recommended)")
        elif "$bcrypt" in hash1:
            print("  ✅ SECURE: Using bcrypt (good)")
        elif "$pbkdf2" in hash1:
            print("  ⚠️  WARNING: Using PBKDF2 (consider Argon2)")
        else:
            self.vulnerabilities.append("CRITICAL: Weak or unknown hash algorithm!")
            print("  ❌ VULNERABLE: Weak hash algorithm")
        
        return len(self.vulnerabilities) == 0
    
    async def run_all_tests(self):
        """Run all security penetration tests."""
        print("=" * 60)
        print("SECURITY PENETRATION TESTING SUITE")
        print("=" * 60)
        
        tests = [
            ("Privilege Escalation", self.test_privilege_escalation_guest_to_admin),
            ("Authentication Bypass", self.test_authentication_bypass),
            ("Token Manipulation", self.test_token_manipulation),
            ("QR Code Security", self.test_qr_code_security),
            ("DOS Protection", self.test_dos_and_rate_limiting),
            ("Cryptographic Security", self.test_cryptographic_weaknesses),
        ]
        
        passed = 0
        failed = 0
        
        for name, test_func in tests:
            try:
                result = await test_func()
                if result:
                    passed += 1
                    self.results.append(f"✅ {name}: PASSED")
                else:
                    failed += 1
                    self.results.append(f"❌ {name}: FAILED")
            except Exception as e:
                failed += 1
                self.results.append(f"❌ {name}: ERROR - {e}")
                print(f"\n  ERROR in {name}: {e}")
        
        # Print summary
        print("\n" + "=" * 60)
        print("SECURITY TEST SUMMARY")
        print("=" * 60)
        
        for result in self.results:
            print(result)
        
        print(f"\nTotal: {passed} passed, {failed} failed")
        
        if self.vulnerabilities:
            print("\n" + "=" * 60)
            print("⚠️  CRITICAL VULNERABILITIES FOUND:")
            print("=" * 60)
            for vuln in self.vulnerabilities:
                print(f"  • {vuln}")
            return False
        else:
            print("\n" + "=" * 60)
            print("✅ NO CRITICAL VULNERABILITIES FOUND")
            print("=" * 60)
            return True


async def main():
    """Run security penetration tests."""
    tester = SecurityPenetrationTests()
    success = await tester.run_all_tests()
    
    if not success:
        print("\n⚠️  Security tests found vulnerabilities that need addressing!")
        return 1
    
    print("\n✅ All security tests passed!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)