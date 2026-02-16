"""Our own registry client (Phase 3 -- stub for now)."""

from __future__ import annotations

from writ.core.models import AgentConfig


class RegistryClient:
    """Client for the enwrit registry API.

    Phase 1: Stub -- all operations return graceful failures.
    Phase 3: Full implementation with httpx + auth.
    """

    def __init__(self, base_url: str = "https://api.enwrit.com") -> None:
        self.base_url = base_url

    def push_to_library(self, name: str, agent: AgentConfig) -> bool:
        """Push an agent to the remote personal library."""
        # Phase 3: POST /api/library/{name}
        return False

    def pull_from_library(self, name: str) -> dict | None:
        """Pull an agent from the remote personal library."""
        # Phase 3: GET /api/library/{name}
        return None

    def list_library(self) -> dict:
        """List all agents in remote personal library."""
        # Phase 3: GET /api/library
        return {}

    def search(self, query: str, sort: str = "score") -> list[dict]:
        """Search the public registry."""
        # Phase 3: GET /api/agents?q={query}&sort={sort}
        return []

    def publish(self, agent: AgentConfig) -> bool:
        """Publish an agent to the public registry."""
        # Phase 3: POST /api/agents
        return False
