"""
Authentication: JWT-based login.
Single admin user, credentials stored in .env.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import hmac
import base64

from app.core.config import get_settings

settings = get_settings()
security = HTTPBearer(auto_error=False)


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_token(username: str, role: str = "admin", expires_hours: int = 72) -> str:
    """Create a simple HMAC-signed JWT-like token."""
    header = _b64_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_data = {
        "sub": username,
        "role": role,
        "exp": (datetime.utcnow() + timedelta(hours=expires_hours)).timestamp(),
        "iat": datetime.utcnow().timestamp(),
    }
    payload = _b64_encode(json.dumps(payload_data).encode())
    signature = hmac.new(
        settings.secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    sig = _b64_encode(signature)
    return f"{header}.{payload}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode token. Returns payload or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts

        # Verify signature
        expected_sig = hmac.new(
            settings.secret_key.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64_decode(sig), expected_sig):
            return None

        # Decode payload
        data = json.loads(_b64_decode(payload))

        # Check expiration
        if data.get("exp", 0) < datetime.utcnow().timestamp():
            return None

        return data
    except Exception:
        return None


def verify_password(plain: str, hashed: str) -> bool:
    """Simple SHA256 hash comparison."""
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


def hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Dependency: require valid JWT on all protected routes."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency: require admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
