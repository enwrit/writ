"""Client for the enwrit platform API (api.enwrit.com).

Handles personal library sync (push/pull agents) and future registry operations.
All calls degrade gracefully -- network errors never crash the CLI.
"""

from __future__ import annotations

import logging

import httpx

from writ.core import auth
from writ.core.models import AgentConfig
from writ.utils import yaml_dumps

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0  # seconds


class RegistryClient:
    """Client for the enwrit platform API.

    Uses the auth token from ~/.writ/config.yaml (set by ``writ login``).
    Every public method catches network/HTTP errors and returns a safe default
    so the CLI never breaks when the backend is unreachable.
    """

    def __init__(self, base_url: str | None = None) -> None:
        from writ.core.store import load_global_config

        cfg = load_global_config()
        self.base_url = (base_url or cfg.registry_url).rstrip("/")
        self._token = auth.get_token()

    # -- helpers -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # -- personal library ----------------------------------------------------

    def push_to_library(
        self, name: str, agent: AgentConfig, *, is_public: bool = False,
    ) -> bool:
        """Upsert an agent to the remote personal library.

        Returns True on success, False on any failure.
        """
        try:
            payload = {
                "name": name,
                "description": agent.description,
                "version": agent.version,
                "tags": agent.tags,
                "instructions": agent.instructions,
                "config_yaml": yaml_dumps(agent.model_dump(mode="json")),
                "is_public": is_public,
            }
            resp = httpx.post(
                f"{self.base_url}/library/agents",
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return True
            logger.debug("push_to_library %s: HTTP %s", name, resp.status_code)
            return False
        except Exception:  # noqa: BLE001
            logger.debug("push_to_library %s: network error", name, exc_info=True)
            return False

    def pull_from_library(self, name: str) -> dict | None:
        """Pull a single agent from the remote library.

        Returns the agent data dict on success, None on failure.
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/library/agents/{name}",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:  # noqa: BLE001
            logger.debug("pull_from_library %s: network error", name, exc_info=True)
            return None

    def list_library(self) -> list[dict]:
        """List all agents in the remote personal library (metadata only).

        Returns a list of agent summary dicts, or empty list on failure.
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/library/agents",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("agents", [])
            return []
        except Exception:  # noqa: BLE001
            logger.debug("list_library: network error", exc_info=True)
            return []

    # -- public registry -------------------------------------------------------

    def search(
        self, query: str, *, limit: int = 20,
    ) -> list[dict]:
        """Search the public agent registry (no auth required)."""
        try:
            resp = httpx.get(
                f"{self.base_url}/agents",
                params={"q": query, "limit": limit},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("agents", [])
            return []
        except Exception:  # noqa: BLE001
            return []

    def pull_public_agent(self, name: str) -> dict | None:
        """Pull a public agent by name (no auth required)."""
        try:
            resp = httpx.get(
                f"{self.base_url}/agents/{name}",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:  # noqa: BLE001
            return None
