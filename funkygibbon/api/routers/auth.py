"""
Authentication API endpoints.

Provides admin password login and guest QR code access.
"""

from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import timedelta
import json
import os

from ...auth import (
    PasswordManager, TokenManager, QRCodeManager,
    auth_rate_limiter, rate_limit_decorator,
    audit_logger, SecurityEventType, get_request_info
)


# Initialize router
router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# Initialize managers (in production, these would be singleton instances)
password_manager = PasswordManager()
token_manager = TokenManager(secret_key=os.getenv("JWT_SECRET", "development-secret-key"))
qr_manager = QRCodeManager()

# Load admin password hash from config
# In production, this would come from a configuration file
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")


# Request/Response models
class AdminLoginRequest(BaseModel):
    """Admin login request."""
    password: str = Field(..., min_length=1, description="Admin password")


class GuestAccessRequest(BaseModel):
    """Guest access generation request."""
    duration_hours: Optional[int] = Field(24, ge=1, le=168, description="Token validity in hours (max 7 days)")
    custom_server: Optional[str] = Field(None, description="Custom server address for QR code")


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class QRCodeResponse(BaseModel):
    """QR code generation response."""
    qr_code: str = Field(..., description="Base64 encoded QR code image")
    qr_data: Dict[str, Any] = Field(..., description="Data encoded in QR code")
    expires_in: int = Field(..., description="Token expiration in seconds")


class GuestTokenVerifyRequest(BaseModel):
    """Guest token verification request."""
    token: str = Field(..., min_length=1, description="Guest access token")


# Helper to extract client IP
async def get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Direct connection
    if request.client:
        return request.client.host
    return "unknown"


# Dependency for admin authentication
async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Verify admin authentication.

    Returns:
        Token payload if valid

    Raises:
        HTTPException: If not authenticated or not admin
    """
    token = credentials.credentials
    client_ip = await get_client_ip(request)

    payload = token_manager.verify_token(token)

    if not payload:
        # Log invalid token
        audit_logger.log_token_event(
            event_type=SecurityEventType.TOKEN_INVALID,
            identifier=client_ip,
            request_info=get_request_info(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    if payload.get("role") != "admin":
        # Log permission denial
        audit_logger.log_permission_check(
            granted=False,
            identifier=client_ip,
            user_id=payload.get("sub", "unknown"),
            role=payload.get("role", "unknown"),
            resource="admin",
            action="access",
            request_info=get_request_info(request)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # Log successful verification
    audit_logger.log_token_event(
        event_type=SecurityEventType.TOKEN_VERIFIED,
        identifier=client_ip,
        user_id=payload.get("sub"),
        role=payload.get("role"),
        request_info=get_request_info(request)
    )

    return payload


# Dependency for any authenticated user
async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Verify any authentication (admin or guest).

    Returns:
        Token payload if valid

    Raises:
        HTTPException: If not authenticated
    """
    token = credentials.credentials
    client_ip = await get_client_ip(request)

    payload = token_manager.verify_token(token)

    if not payload:
        # Log invalid token
        audit_logger.log_token_event(
            event_type=SecurityEventType.TOKEN_INVALID,
            identifier=client_ip,
            request_info=get_request_info(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Log successful verification
    audit_logger.log_token_event(
        event_type=SecurityEventType.TOKEN_VERIFIED,
        identifier=client_ip,
        user_id=payload.get("sub"),
        role=payload.get("role"),
        request_info=get_request_info(request)
    )

    return payload


# Endpoints
@router.post("/admin/login", response_model=TokenResponse)
@rate_limit_decorator(lambda request, login_request: get_client_ip(request))
async def admin_login(
    request: Request,
    login_request: AdminLoginRequest
):
    """
    Authenticate admin with password.

    Returns JWT token for admin access.
    """
    client_ip = await get_client_ip(request)
    request_info = get_request_info(request)

    try:
        if not ADMIN_PASSWORD_HASH:
            # For development/testing when no password is set
            if login_request.password == "admin":
                # Log successful authentication
                audit_logger.log_auth_attempt(
                    success=True,
                    identifier=client_ip,
                    user_id="admin",
                    role="admin",
                    request_info=request_info
                )

                token = token_manager.create_token(
                    user_id="admin",
                    role="admin",
                    permissions=["read", "write", "delete", "configure"],
                    expires_delta=timedelta(days=7)
                )

                # Log token creation
                audit_logger.log_token_event(
                    event_type=SecurityEventType.TOKEN_CREATED,
                    identifier=client_ip,
                    user_id="admin",
                    role="admin",
                    token_type="jwt",
                    request_info=request_info
                )

                return TokenResponse(
                    access_token=token,
                    expires_in=7 * 24 * 3600,  # 7 days in seconds
                    role="admin"
                )
            else:
                # Log failed authentication
                audit_logger.log_auth_attempt(
                    success=False,
                    identifier=client_ip,
                    reason="Invalid password",
                    request_info=request_info
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid password"
                )

        # Verify password against stored hash
        is_valid, new_hash = password_manager.verify_password(login_request.password, ADMIN_PASSWORD_HASH)

        if not is_valid:
            # Log failed authentication
            audit_logger.log_auth_attempt(
                success=False,
                identifier=client_ip,
                reason="Invalid password",
                request_info=request_info
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )

        # Log successful authentication
        audit_logger.log_auth_attempt(
            success=True,
            identifier=client_ip,
            user_id="admin",
            role="admin",
            request_info=request_info
        )

        # TODO: If new_hash is provided, update the stored hash

        # Create admin token
        token = token_manager.create_token(
            user_id="admin",
            role="admin",
            permissions=["read", "write", "delete", "configure"],
            expires_delta=timedelta(days=7)
        )

        # Log token creation
        audit_logger.log_token_event(
            event_type=SecurityEventType.TOKEN_CREATED,
            identifier=client_ip,
            user_id="admin",
            role="admin",
            token_type="jwt",
            request_info=request_info
        )

        return TokenResponse(
            access_token=token,
            expires_in=7 * 24 * 3600,  # 7 days in seconds
            role="admin"
        )

    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected error
        audit_logger.log_event(
            event_type=SecurityEventType.AUTH_FAILURE,
            identifier=client_ip,
            details={"error": str(e)},
            request_info=request_info
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error"
        )


@router.post("/guest/generate-qr", response_model=QRCodeResponse)
async def generate_guest_qr(
    request: Request,
    guest_request: GuestAccessRequest,
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    Generate QR code for guest access (admin only).

    Creates a QR code containing server information and a guest token.
    """
    client_ip = await get_client_ip(request)
    request_info = get_request_info(request)

    # Create guest token
    guest_token = token_manager.create_guest_token(duration_hours=guest_request.duration_hours)

    # Generate QR code
    qr_data, qr_image = qr_manager.generate_guest_qr(
        guest_token=guest_token,
        duration_hours=guest_request.duration_hours,
        custom_server=guest_request.custom_server
    )

    # Log QR generation
    audit_logger.log_event(
        event_type=SecurityEventType.GUEST_QR_GENERATED,
        identifier=client_ip,
        user_id=admin.get("sub"),
        role=admin.get("role"),
        details={
            "duration_hours": guest_request.duration_hours,
            "server": guest_request.custom_server or "default"
        },
        request_info=request_info
    )

    return QRCodeResponse(
        qr_code=qr_image,
        qr_data=qr_data,
        expires_in=guest_request.duration_hours * 3600
    )


@router.post("/guest/verify", response_model=TokenResponse)
@rate_limit_decorator(lambda request, token_request: get_client_ip(request))
async def verify_guest_token(
    request: Request,
    token_request: GuestTokenVerifyRequest
):
    """
    Verify guest token from QR code.

    Exchanges a guest token for a JWT.
    """
    client_ip = await get_client_ip(request)
    request_info = get_request_info(request)

    # Verify guest token
    token_data = token_manager.verify_guest_token(token_request.token)

    if not token_data:
        # Log failed verification
        audit_logger.log_event(
            event_type=SecurityEventType.TOKEN_INVALID,
            identifier=client_ip,
            details={"token_type": "guest"},
            request_info=request_info
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Calculate remaining validity
    remaining_time = token_data["expires"] - datetime.now(timezone.utc)

    # Create JWT for guest
    guest_id = f"guest_{token_request.token[:8]}"
    jwt_token = token_manager.create_token(
        user_id=guest_id,
        role="guest",
        permissions=token_data["permissions"],
        expires_delta=remaining_time
    )

    # Log guest access granted
    audit_logger.log_event(
        event_type=SecurityEventType.GUEST_ACCESS_GRANTED,
        identifier=client_ip,
        user_id=guest_id,
        role="guest",
        details={
            "expires_in": int(remaining_time.total_seconds())
        },
        request_info=request_info
    )

    return TokenResponse(
        access_token=jwt_token,
        expires_in=int(remaining_time.total_seconds()),
        role="guest"
    )


@router.post("/guest/revoke")
async def revoke_guest_token(
    token: str,
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    Revoke a guest token (admin only).

    Immediately invalidates the specified guest token.
    """
    success = token_manager.revoke_guest_token(token)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )

    return {"message": "Token revoked successfully"}


@router.get("/guest/list")
async def list_guest_tokens(admin: Dict[str, Any] = Depends(require_admin)):
    """
    List active guest tokens (admin only).

    Returns information about all active guest access tokens.
    """
    tokens = token_manager.get_active_guest_tokens()

    return {
        "count": len(tokens),
        "tokens": tokens
    }


@router.get("/me")
async def get_current_user(user: Dict[str, Any] = Depends(require_auth)):
    """
    Get current user information.

    Returns information about the authenticated user.
    """
    return {
        "user_id": user.get("sub"),
        "role": user.get("role"),
        "permissions": user.get("permissions"),
        "expires_at": user.get("exp")
    }


@router.post("/refresh")
async def refresh_token(user: Dict[str, Any] = Depends(require_auth)):
    """
    Refresh authentication token.

    Issues a new token with extended expiration.
    """
    # Only admin tokens can be refreshed
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin tokens can be refreshed"
        )

    # Create new token
    new_token = token_manager.create_token(
        user_id=user.get("sub"),
        role=user.get("role"),
        permissions=user.get("permissions"),
        expires_delta=timedelta(days=7)
    )

    return TokenResponse(
        access_token=new_token,
        expires_in=7 * 24 * 3600,
        role="admin"
    )


# Add missing datetime import
from datetime import datetime, timezone
