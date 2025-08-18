"""
Password management with Argon2id hashing.

Provides secure password hashing and verification for admin authentication.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from typing import Tuple, Optional


class PasswordManager:
    """Manage password hashing and verification using Argon2id."""

    def __init__(self):
        """Initialize with secure Argon2id parameters."""
        self.ph = PasswordHasher(
            time_cost=2,  # Number of iterations
            memory_cost=65536,  # Memory usage in KB (64MB)
            parallelism=1,  # Number of parallel threads
            hash_len=32,  # Length of the hash in bytes
            salt_len=16  # Length of random salt in bytes
        )

    def hash_password(self, password: str) -> str:
        """
        Hash a password using Argon2id.

        Args:
            password: Plain text password to hash

        Returns:
            Hashed password string
        """
        if not password:
            raise ValueError("Password cannot be empty")

        return self.ph.hash(password)

    def verify_password(self, password: str, hash: str) -> Tuple[bool, Optional[str]]:
        """
        Verify a password against a hash.

        Args:
            password: Plain text password to verify
            hash: Stored password hash

        Returns:
            Tuple of (is_valid, new_hash_if_needed)
            - is_valid: True if password matches
            - new_hash_if_needed: New hash if rehashing is recommended
        """
        try:
            self.ph.verify(hash, password)

            # Check if hash needs to be updated (parameters changed)
            if self.ph.check_needs_rehash(hash):
                new_hash = self.ph.hash(password)
                return True, new_hash

            return True, None

        except VerifyMismatchError:
            return False, None
        except InvalidHash:
            return False, None

    def check_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        Check if password meets minimum security requirements.

        Args:
            password: Password to check

        Returns:
            Tuple of (is_strong, message)
        """
        if len(password) < 12:
            return False, "Password must be at least 12 characters long"

        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)

        if not has_upper:
            return False, "Password must contain at least one uppercase letter"
        if not has_lower:
            return False, "Password must contain at least one lowercase letter"
        if not has_digit:
            return False, "Password must contain at least one digit"
        if not has_special:
            return False, "Password must contain at least one special character"

        return True, "Password meets security requirements"
