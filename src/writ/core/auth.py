"""Authentication state management for registry sync.

Phase 1: Stub -- all remote operations gracefully degrade.
Phase 3: GitHub OAuth token management.
"""

from __future__ import annotations

from writ.core import store


def is_logged_in() -> bool:
    """Check if the user has a valid auth token."""
    config = store.load_global_config()
    return config.auth_token is not None


def get_token() -> str | None:
    """Get the stored auth token, or None if not authenticated."""
    config = store.load_global_config()
    return config.auth_token


def save_token(token: str) -> None:
    """Save an auth token to global config."""
    config = store.load_global_config()
    config.auth_token = token
    store.save_global_config(config)


def clear_token() -> None:
    """Remove the stored auth token."""
    config = store.load_global_config()
    config.auth_token = None
    store.save_global_config(config)
