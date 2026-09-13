"""Shared FastAPI authentication and Supabase error dependencies.

Routers import these dependency functions directly so FastAPI's dependency
override keys remain stable across the application.  The gateway is
caller-token scoped; it never introduces a service-role credential.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException

from ginseng.supabase import (
    AuthenticatedIdentity,
    SupabaseAuthenticationError,
    SupabaseConfigurationError,
    SupabaseConflictError,
    SupabaseError,
    SupabaseGateway,
    SupabaseUnavailableError,
    SupabaseValidationError,
)

_SUPABASE_GATEWAY = SupabaseGateway()


def supabase_http_error(error: SupabaseError) -> HTTPException:
    """Map trusted Supabase boundary failures to stable public HTTP errors."""
    if isinstance(error, SupabaseAuthenticationError):
        return HTTPException(status_code=401, detail="Your session is invalid. Sign in again.")
    if isinstance(error, SupabaseConflictError):
        return HTTPException(status_code=409, detail="Workspace changed. Reload before saving.")
    if isinstance(error, SupabaseValidationError):
        return HTTPException(status_code=422, detail="Workspace data is invalid. Review the amounts and dates.")
    if isinstance(error, (SupabaseConfigurationError, SupabaseUnavailableError)):
        return HTTPException(status_code=503, detail="Workspace service is unavailable.")
    return HTTPException(status_code=503, detail="Workspace service is unavailable.")


def require_identity(authorization: Annotated[str | None, Header()] = None) -> AuthenticatedIdentity:
    """Authenticate one bearer token for a protected route."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Sign in to use Ginseng.")
    scheme, _, access_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not access_token or access_token.strip() != access_token:
        raise HTTPException(status_code=401, detail="Your session is invalid. Sign in again.")
    try:
        return _SUPABASE_GATEWAY.authenticate(access_token)
    except SupabaseError as error:
        raise supabase_http_error(error) from error


def get_supabase_gateway() -> SupabaseGateway:
    """Return the shared caller-scoped gateway used by repository dependencies."""
    return _SUPABASE_GATEWAY
