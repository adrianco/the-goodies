"""
Audit logging for security events.

Provides comprehensive logging of authentication attempts, permission violations,
and suspicious patterns.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from enum import Enum
from pathlib import Path
import asyncio
from collections import defaultdict
import uuid


class SecurityEventType(Enum):
    """Types of security events to log."""
    # Authentication events
    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    AUTH_LOCKOUT = "auth.lockout"

    # Token events
    TOKEN_CREATED = "token.created"
    TOKEN_VERIFIED = "token.verified"
    TOKEN_EXPIRED = "token.expired"
    TOKEN_INVALID = "token.invalid"
    TOKEN_REVOKED = "token.revoked"

    # Access control events
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"

    # Guest access events
    GUEST_QR_GENERATED = "guest.qr_generated"
    GUEST_TOKEN_CREATED = "guest.token_created"
    GUEST_ACCESS_GRANTED = "guest.access_granted"

    # Suspicious activity
    SUSPICIOUS_PATTERN = "suspicious.pattern"
    RATE_LIMIT_EXCEEDED = "suspicious.rate_limit"
    INVALID_TOKEN_ALGORITHM = "suspicious.token_algorithm"


class AuditLogger:
    """
    Comprehensive audit logger for security events.

    Features:
    - Structured logging with event types
    - Automatic suspicious pattern detection
    - Log rotation and archival
    - Query and analysis capabilities
    """

    def __init__(
        self,
        log_file: Optional[str] = None,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
        retention_days: int = 90,
        enable_pattern_detection: bool = True
    ):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file
            max_file_size: Maximum log file size before rotation
            retention_days: Days to retain logs
            enable_pattern_detection: Enable suspicious pattern detection
        """
        self.log_file = log_file or "audit.log"
        self.max_file_size = max_file_size
        self.retention_days = retention_days
        self.enable_pattern_detection = enable_pattern_detection

        # Setup logger
        self._setup_logger()

        # Pattern detection state
        self._failed_attempts = defaultdict(list)
        self._pattern_detection_task = None

    def _setup_logger(self):
        """Configure the audit logger."""
        self.logger = logging.getLogger("funkygibbon.audit")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers.clear()

        # Console handler for development
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # File handler with rotation
        if self.log_file:
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=self.max_file_size,
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.INFO)

            # JSON formatter for structured logs
            file_formatter = logging.Formatter('%(message)s')
            file_handler.setFormatter(file_formatter)

            self.logger.addHandler(file_handler)

    async def start_pattern_detection(self):
        """Start background pattern detection task."""
        if self.enable_pattern_detection:
            self._pattern_detection_task = asyncio.create_task(
                self._pattern_detection_loop()
            )

    async def stop_pattern_detection(self):
        """Stop background pattern detection task."""
        if self._pattern_detection_task:
            self._pattern_detection_task.cancel()
            try:
                await self._pattern_detection_task
            except asyncio.CancelledError:
                pass

    async def _pattern_detection_loop(self):
        """Background task to detect suspicious patterns."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                self._detect_suspicious_patterns()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Pattern detection error: {e}")

    def _detect_suspicious_patterns(self):
        """Detect and log suspicious patterns."""
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time.timestamp() - 300  # 5 minutes

        for identifier, attempts in list(self._failed_attempts.items()):
            # Filter recent attempts
            recent_attempts = [
                (timestamp, details) for timestamp, details in attempts
                if timestamp > cutoff_time
            ]

            # Update stored attempts
            if recent_attempts:
                self._failed_attempts[identifier] = recent_attempts
            else:
                del self._failed_attempts[identifier]
                continue

            # Check for suspicious patterns
            if len(recent_attempts) >= 10:
                # Many failed attempts from same source
                self.log_event(
                    SecurityEventType.SUSPICIOUS_PATTERN,
                    identifier=identifier,
                    details={
                        "pattern": "excessive_failed_attempts",
                        "count": len(recent_attempts),
                        "time_window": "5_minutes"
                    }
                )

            # Check for credential stuffing pattern
            unique_passwords = set(
                details.get("password_hash", "")[:8]  # First 8 chars of hash
                for _, details in recent_attempts
            )
            if len(unique_passwords) >= 5:
                self.log_event(
                    SecurityEventType.SUSPICIOUS_PATTERN,
                    identifier=identifier,
                    details={
                        "pattern": "credential_stuffing",
                        "unique_attempts": len(unique_passwords),
                        "time_window": "5_minutes"
                    }
                )

    def log_event(
        self,
        event_type: SecurityEventType,
        identifier: Optional[str] = None,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_info: Optional[Dict[str, Any]] = None
    ):
        """
        Log a security event.

        Args:
            event_type: Type of security event
            identifier: Request identifier (e.g., IP address)
            user_id: User ID if available
            role: User role if available
            details: Additional event details
            request_info: Request information (path, method, etc.)
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type.value,
            "identifier": identifier,
            "user_id": user_id,
            "role": role,
            "details": details or {},
            "request_info": request_info or {}
        }

        # Log as JSON
        self.logger.info(json.dumps(event))

        # Track failed authentication attempts for pattern detection
        if event_type == SecurityEventType.AUTH_FAILURE and identifier:
            self._failed_attempts[identifier].append(
                (datetime.now(timezone.utc).timestamp(), details or {})
            )

    def log_auth_attempt(
        self,
        success: bool,
        identifier: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        reason: Optional[str] = None,
        request_info: Optional[Dict[str, Any]] = None
    ):
        """
        Log authentication attempt.

        Args:
            success: Whether authentication succeeded
            identifier: Request identifier
            user_id: User ID if available
            role: User role if available
            reason: Failure reason if applicable
            request_info: Request information
        """
        event_type = (
            SecurityEventType.AUTH_SUCCESS if success
            else SecurityEventType.AUTH_FAILURE
        )

        details = {}
        if reason:
            details["reason"] = reason

        self.log_event(
            event_type=event_type,
            identifier=identifier,
            user_id=user_id,
            role=role,
            details=details,
            request_info=request_info
        )

    def log_permission_check(
        self,
        granted: bool,
        identifier: str,
        user_id: str,
        role: str,
        resource: str,
        action: str,
        request_info: Optional[Dict[str, Any]] = None
    ):
        """
        Log permission check.

        Args:
            granted: Whether permission was granted
            identifier: Request identifier
            user_id: User ID
            role: User role
            resource: Resource being accessed
            action: Action being performed
            request_info: Request information
        """
        event_type = (
            SecurityEventType.PERMISSION_GRANTED if granted
            else SecurityEventType.PERMISSION_DENIED
        )

        self.log_event(
            event_type=event_type,
            identifier=identifier,
            user_id=user_id,
            role=role,
            details={
                "resource": resource,
                "action": action
            },
            request_info=request_info
        )

    def log_token_event(
        self,
        event_type: SecurityEventType,
        identifier: str,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        token_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_info: Optional[Dict[str, Any]] = None
    ):
        """
        Log token-related event.

        Args:
            event_type: Token event type
            identifier: Request identifier
            user_id: User ID if available
            role: User role if available
            token_type: Type of token (jwt, guest, etc.)
            details: Additional details
            request_info: Request information
        """
        event_details = details or {}
        if token_type:
            event_details["token_type"] = token_type

        self.log_event(
            event_type=event_type,
            identifier=identifier,
            user_id=user_id,
            role=role,
            details=event_details,
            request_info=request_info
        )

    def query_logs(
        self,
        event_types: Optional[List[SecurityEventType]] = None,
        identifier: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query audit logs.

        Args:
            event_types: Filter by event types
            identifier: Filter by identifier
            user_id: Filter by user ID
            start_time: Start time for query
            end_time: End time for query
            limit: Maximum results to return

        Returns:
            List of matching log entries
        """
        # In production, this would query from a database
        # For now, return empty list as this is a placeholder
        return []

    def generate_report(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Generate security report for time period.

        Args:
            start_time: Report start time
            end_time: Report end time

        Returns:
            Security report with statistics and patterns
        """
        # In production, this would analyze logs from database
        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "summary": {
                "total_events": 0,
                "auth_attempts": 0,
                "auth_failures": 0,
                "permission_denials": 0,
                "suspicious_patterns": 0
            },
            "top_identifiers": [],
            "patterns_detected": []
        }


# Global audit logger instance
audit_logger = AuditLogger(
    log_file="security_audit.log",
    enable_pattern_detection=True
)


def get_request_info(request) -> Dict[str, Any]:
    """
    Extract request information for audit logging.

    Args:
        request: FastAPI request object

    Returns:
        Dictionary with request information
    """
    return {
        "method": request.method,
        "path": request.url.path,
        "client_host": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
