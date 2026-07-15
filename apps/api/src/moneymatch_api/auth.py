"""Supabase JWT verification.

The API trusts nothing but a valid Supabase token. Two verification modes:
- HS256 with the project JWT secret (`SUPABASE_JWT_SECRET`), or
- asymmetric via JWKS (`resolved_jwks_url`), keys cached by PyJWT.

Verified claims become an `AuthedIdentity`; the DB user row is provisioned from
it (see `services.user_service`). No client-supplied identity is ever trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from .config import Settings, get_settings
from .errors import APIError


class AuthError(APIError):
    def __init__(self, message: str = "Not authenticated") -> None:
        super().__init__("unauthenticated", message, status_code=401)


@dataclass(frozen=True)
class AuthedIdentity:
    """Verified identity from a Supabase JWT."""

    auth_id: str
    email: str | None


@lru_cache
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True)


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthError("Malformed Authorization header")
    return parts[1].strip()


def verify_token(token: str, settings: Settings | None = None) -> AuthedIdentity:
    """Verify a Supabase JWT and return the identity, or raise AuthError."""
    settings = settings or get_settings()
    try:
        if settings.supabase_jwt_secret:
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
            )
        else:
            jwks_url = settings.resolved_jwks_url
            if not jwks_url:  # pragma: no cover - guarded by config validation
                raise AuthError("Auth not configured")
            signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.supabase_jwt_audience,
            )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc

    sub = claims.get("sub")
    if not sub:
        raise AuthError("Token missing subject")
    email = claims.get("email")
    return AuthedIdentity(auth_id=str(sub), email=email)
