"""
Tests for audit logging functionality.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from io import StringIO
import pytest

from funkygibbon.auth.audit_logger import AuditLogger, SecurityEventType


class TestAuditLogger:
    """Test audit logging functionality."""

    def test_audit_logger_init(self):
        """Test audit logger initialization."""
        logger = AuditLogger(
            log_file="test_audit.log",
            max_file_size=1024,
            retention_days=30
        )

        assert logger.log_file == "test_audit.log"
        assert logger.max_file_size == 1024
        assert logger.retention_days == 30
        assert logger.enable_pattern_detection is True

    def test_log_event_structure(self):
        """Test event logging structure."""
        # Capture log output
        log_capture_string = StringIO()
        ch = logging.StreamHandler(log_capture_string)

        logger = AuditLogger()
        logger.logger.handlers.clear()
        logger.logger.addHandler(ch)
        logger.logger.setLevel(logging.INFO)

        # Log an event
        logger.log_event(
            event_type=SecurityEventType.AUTH_SUCCESS,
            identifier="192.168.1.1",
            user_id="admin",
            role="admin",
            details={"method": "password"},
            request_info={"path": "/auth/login", "method": "POST"}
        )

        # Get logged content
        log_contents = log_capture_string.getvalue()

        # Parse JSON
        event = json.loads(log_contents.strip())

        # Verify structure
        assert "event_id" in event
        assert "timestamp" in event
        assert event["event_type"] == "auth.success"
        assert event["identifier"] == "192.168.1.1"
        assert event["user_id"] == "admin"
        assert event["role"] == "admin"
        assert event["details"]["method"] == "password"
        assert event["request_info"]["path"] == "/auth/login"

    def test_log_auth_attempt_success(self):
        """Test logging successful authentication."""
        log_capture_string = StringIO()
        ch = logging.StreamHandler(log_capture_string)

        logger = AuditLogger()
        logger.logger.handlers.clear()
        logger.logger.addHandler(ch)

        logger.log_auth_attempt(
            success=True,
            identifier="192.168.1.1",
            user_id="admin",
            role="admin"
        )

        event = json.loads(log_capture_string.getvalue().strip())
        assert event["event_type"] == "auth.success"
        assert event["user_id"] == "admin"

    def test_log_auth_attempt_failure(self):
        """Test logging failed authentication."""
        log_capture_string = StringIO()
        ch = logging.StreamHandler(log_capture_string)

        logger = AuditLogger()
        logger.logger.handlers.clear()
        logger.logger.addHandler(ch)

        logger.log_auth_attempt(
            success=False,
            identifier="192.168.1.1",
            reason="Invalid password"
        )

        event = json.loads(log_capture_string.getvalue().strip())
        assert event["event_type"] == "auth.failure"
        assert event["details"]["reason"] == "Invalid password"

    def test_log_permission_check(self):
        """Test logging permission checks."""
        log_capture_string = StringIO()
        ch = logging.StreamHandler(log_capture_string)

        logger = AuditLogger()
        logger.logger.handlers.clear()
        logger.logger.addHandler(ch)

        # Log granted permission
        logger.log_permission_check(
            granted=True,
            identifier="192.168.1.1",
            user_id="user1",
            role="guest",
            resource="graph",
            action="read"
        )

        event = json.loads(log_capture_string.getvalue().strip())
        assert event["event_type"] == "permission.granted"
        assert event["details"]["resource"] == "graph"
        assert event["details"]["action"] == "read"

    def test_log_token_events(self):
        """Test logging token-related events."""
        log_capture_string = StringIO()
        ch = logging.StreamHandler(log_capture_string)

        logger = AuditLogger()
        logger.logger.handlers.clear()
        logger.logger.addHandler(ch)

        logger.log_token_event(
            event_type=SecurityEventType.TOKEN_CREATED,
            identifier="192.168.1.1",
            user_id="admin",
            role="admin",
            token_type="jwt"
        )

        event = json.loads(log_capture_string.getvalue().strip())
        assert event["event_type"] == "token.created"
        assert event["details"]["token_type"] == "jwt"

    def test_failed_attempt_tracking(self):
        """Test tracking of failed authentication attempts."""
        logger = AuditLogger(enable_pattern_detection=True)

        # Log multiple failures
        for i in range(5):
            logger.log_auth_attempt(
                success=False,
                identifier="192.168.1.1",
                reason="Invalid password"
            )

        # Check tracked attempts
        assert "192.168.1.1" in logger._failed_attempts
        assert len(logger._failed_attempts["192.168.1.1"]) == 5

    def test_suspicious_pattern_detection(self):
        """Test detection of suspicious patterns."""
        log_capture_string = StringIO()
        ch = logging.StreamHandler(log_capture_string)

        logger = AuditLogger(enable_pattern_detection=True)
        logger.logger.handlers.clear()
        logger.logger.addHandler(ch)

        # Simulate many failed attempts
        for i in range(11):
            logger._failed_attempts["192.168.1.1"].append(
                (datetime.now(timezone.utc).timestamp(), {"attempt": i})
            )

        # Run pattern detection
        logger._detect_suspicious_patterns()

        # Check for suspicious pattern log
        logs = log_capture_string.getvalue()
        assert "suspicious.pattern" in logs
        assert "excessive_failed_attempts" in logs

    def test_get_request_info(self):
        """Test request info extraction."""
        from funkygibbon.auth.audit_logger import get_request_info

        # Mock request object
        class MockRequest:
            method = "POST"
            url = type('obj', (object,), {'path': '/auth/login'})
            headers = {"user-agent": "Test Agent"}
            client = type('obj', (object,), {'host': '192.168.1.1'})

        request_info = get_request_info(MockRequest())

        assert request_info["method"] == "POST"
        assert request_info["path"] == "/auth/login"
        assert request_info["client_host"] == "192.168.1.1"
        assert request_info["user_agent"] == "Test Agent"
        assert "timestamp" in request_info

    @pytest.mark.asyncio
    async def test_pattern_detection_task_lifecycle(self):
        """Test background pattern detection task."""
        logger = AuditLogger(enable_pattern_detection=True)

        # Start pattern detection
        await logger.start_pattern_detection()

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Stop pattern detection
        await logger.stop_pattern_detection()

        # Should complete without errors
        assert True

    def test_security_event_types(self):
        """Test all security event types are defined."""
        # Authentication events
        assert SecurityEventType.AUTH_SUCCESS.value == "auth.success"
        assert SecurityEventType.AUTH_FAILURE.value == "auth.failure"
        assert SecurityEventType.AUTH_LOCKOUT.value == "auth.lockout"

        # Token events
        assert SecurityEventType.TOKEN_CREATED.value == "token.created"
        assert SecurityEventType.TOKEN_VERIFIED.value == "token.verified"
        assert SecurityEventType.TOKEN_EXPIRED.value == "token.expired"
        assert SecurityEventType.TOKEN_INVALID.value == "token.invalid"
        assert SecurityEventType.TOKEN_REVOKED.value == "token.revoked"

        # Permission events
        assert SecurityEventType.PERMISSION_GRANTED.value == "permission.granted"
        assert SecurityEventType.PERMISSION_DENIED.value == "permission.denied"

        # Guest access events
        assert SecurityEventType.GUEST_QR_GENERATED.value == "guest.qr_generated"
        assert SecurityEventType.GUEST_TOKEN_CREATED.value == "guest.token_created"
        assert SecurityEventType.GUEST_ACCESS_GRANTED.value == "guest.access_granted"

        # Suspicious activity
        assert SecurityEventType.SUSPICIOUS_PATTERN.value == "suspicious.pattern"
        assert SecurityEventType.RATE_LIMIT_EXCEEDED.value == "suspicious.rate_limit"
        assert SecurityEventType.INVALID_TOKEN_ALGORITHM.value == "suspicious.token_algorithm"
