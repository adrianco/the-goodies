"""
JWT token management for authentication.

Handles creation and verification of JWT tokens for admin and guest access.
"""

import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
import secrets


class TokenManager:
    """Manage JWT tokens for authentication."""
    
    def __init__(self, secret_key: str = None):
        """
        Initialize token manager.
        
        Args:
            secret_key: Secret key for signing tokens. If None, generates a random key.
        """
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = "HS256"
        
        # Store active guest tokens for validation
        self.guest_tokens: Dict[str, Dict[str, Any]] = {}
    
    def create_token(self,
                    user_id: str,
                    role: str,
                    permissions: List[str],
                    expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT token.
        
        Args:
            user_id: Unique identifier for the user
            role: User role (admin or guest)
            permissions: List of permissions
            expires_delta: Token expiration time
            
        Returns:
            Encoded JWT token
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            # Default expiration based on role
            if role == "admin":
                expire = datetime.now(timezone.utc) + timedelta(days=7)
            else:
                expire = datetime.now(timezone.utc) + timedelta(hours=24)
        
        payload = {
            "sub": user_id,
            "role": role,
            "permissions": permissions,
            "exp": expire,
            "iat": datetime.now(timezone.utc)
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token to verify
            
        Returns:
            Decoded token payload or None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def create_guest_token(self, duration_hours: int = 24) -> str:
        """
        Create a guest access token.
        
        Args:
            duration_hours: Token validity duration in hours
            
        Returns:
            Guest token string
        """
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        
        self.guest_tokens[token] = {
            "expires": expires,
            "permissions": ["read"],
            "created_at": datetime.now(timezone.utc)
        }
        
        return token
    
    def verify_guest_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a guest token.
        
        Args:
            token: Guest token to verify
            
        Returns:
            Token data or None if invalid/expired
        """
        if token not in self.guest_tokens:
            return None
        
        token_data = self.guest_tokens[token]
        
        # Check expiration
        if datetime.now(timezone.utc) > token_data["expires"]:
            del self.guest_tokens[token]
            return None
        
        return token_data
    
    def revoke_guest_token(self, token: str) -> bool:
        """
        Revoke a guest token.
        
        Args:
            token: Guest token to revoke
            
        Returns:
            True if token was revoked, False if not found
        """
        if token in self.guest_tokens:
            del self.guest_tokens[token]
            return True
        return False
    
    def cleanup_expired_tokens(self):
        """Remove expired guest tokens from storage."""
        now = datetime.now(timezone.utc)
        expired = [
            token for token, data in self.guest_tokens.items()
            if now > data["expires"]
        ]
        for token in expired:
            del self.guest_tokens[token]
    
    def get_active_guest_tokens(self) -> List[Dict[str, Any]]:
        """
        Get list of active guest tokens.
        
        Returns:
            List of token information dictionaries
        """
        self.cleanup_expired_tokens()
        
        return [
            {
                "token": token[:8] + "...",  # Show only first 8 chars
                "expires": data["expires"].isoformat(),
                "created_at": data["created_at"].isoformat(),
                "permissions": data["permissions"]
            }
            for token, data in self.guest_tokens.items()
        ]