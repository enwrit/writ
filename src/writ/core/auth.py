"""Authentication and identity management for enwrit.com registry sync.

Manages API key storage and persistent user identity in ~/.writ/config.yaml.
Remote operations degrade gracefully when not authenticated or offline.
"""

from __future__ import annotations

import getpass
import uuid

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


def get_identity() -> str:
    """Return a persistent user identity for message attribution.

    Resolution order:
    1. Stored identity in ~/.writ/config.yaml (persists across sessions)
    2. If logged in, fetch display_name / github_username from enwrit.com
    3. Otherwise, generate from OS username + short random suffix

    Once resolved, the identity is saved so it stays consistent.
    """
    config = store.load_global_config()
    if config.identity:
        return config.identity

    identity: str | None = None

    if config.auth_token:
        identity = _fetch_remote_identity(config.auth_token)

    if not identity:
        try:
            os_user = getpass.getuser()
        except Exception:  # noqa: BLE001
            os_user = "user"
        short_id = uuid.uuid4().hex[:6]
        identity = f"{os_user}-{short_id}"

    config.identity = identity
    store.save_global_config(config)
    return identity


def _fetch_remote_identity(token: str) -> str | None:
    """Try to get display_name or github_username from /auth/me."""
    try:
        import httpx

        from writ.core.store import load_global_config
        base_url = load_global_config().registry_url
        resp = httpx.get(
            f"{base_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("display_name") or data.get("github_username") or None
    except Exception:  # noqa: BLE001
        pass
    return None
