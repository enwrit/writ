"""Client for the enwrit platform API (api.enwrit.com).

Handles personal library sync (push/pull agents) and future registry operations.
All calls degrade gracefully -- network errors never crash the CLI.
"""

from __future__ import annotations

import logging

import httpx

from writ.core import auth
from writ.core.models import InstructionConfig
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
        self, name: str, agent: InstructionConfig, *, is_public: bool = False,
    ) -> bool:
        """Upsert an agent to the remote personal library.

        Returns True on success, False on any failure.
        """
        try:
            payload: dict = {
                "name": name,
                "description": agent.description,
                "version": agent.version,
                "tags": agent.tags,
                "instructions": agent.instructions,
                "config_yaml": yaml_dumps(agent.model_dump(mode="json")),
                "is_public": is_public,
            }
            if agent.task_type:
                payload["task_type"] = agent.task_type
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

    # -- conversation relay ---------------------------------------------------

    def relay_message(
        self,
        *,
        conv_id: str,
        agent_name: str,
        repo_name: str,
        content: str,
        attachments: list[str] | None = None,
        to_user_id: str | None = None,
        goal: str = "",
    ) -> dict | None:
        """Push a message through the backend relay.

        Returns ``{"message_id": ..., "conv_id": ..., "message_count": ...}``
        on success, ``None`` on failure.
        """
        try:
            payload: dict = {
                "conv_id": conv_id,
                "agent_name": agent_name,
                "repo_name": repo_name,
                "content": content,
                "attachments": attachments or [],
                "goal": goal,
            }
            if to_user_id:
                payload["to_user_id"] = to_user_id
            resp = httpx.post(
                f"{self.base_url}/conversations/relay",
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.debug("relay_message: HTTP %s", resp.status_code)
            return None
        except Exception:  # noqa: BLE001
            logger.debug("relay_message: network error", exc_info=True)
            return None

    def pull_conversation(
        self, conv_id: str, *, after_message: int = 0,
    ) -> dict | None:
        """Pull conversation data from the relay.

        Use ``after_message=N`` to only get messages after the Nth one.
        """
        try:
            params: dict = {}
            if after_message > 0:
                params["after_message"] = after_message
            resp = httpx.get(
                f"{self.base_url}/conversations/{conv_id}",
                params=params,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:  # noqa: BLE001
            logger.debug("pull_conversation: network error", exc_info=True)
            return None

    def list_conversations(self, *, unread: bool = False) -> list[dict]:
        """List conversations from the relay."""
        try:
            params: dict = {}
            if unread:
                params["unread"] = "true"
            resp = httpx.get(
                f"{self.base_url}/conversations",
                params=params,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("conversations", [])
            return []
        except Exception:  # noqa: BLE001
            logger.debug("list_conversations: network error", exc_info=True)
            return []

    def update_conversation_status(
        self, conv_id: str, status: str,
    ) -> bool:
        """Update conversation status on the relay."""
        try:
            resp = httpx.patch(
                f"{self.base_url}/conversations/{conv_id}",
                json={"status": status},
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    # -- knowledge: reviews ----------------------------------------------------

    def submit_review(
        self,
        agent_name: str,
        *,
        rating: float,
        summary: str,
        strengths: list[str] | None = None,
        weaknesses: list[str] | None = None,
        context: dict | None = None,
        author_agent: str = "",
        author_repo: str = "",
    ) -> dict | None:
        """Submit a review for a public instruction. Returns review dict or None."""
        try:
            payload: dict = {
                "rating": rating,
                "summary": summary,
                "strengths": strengths or [],
                "weaknesses": weaknesses or [],
                "context": context or {},
                "author_agent": author_agent,
                "author_repo": author_repo,
            }
            resp = httpx.post(
                f"{self.base_url}/agents/{agent_name}/reviews",
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            logger.debug("submit_review %s: HTTP %s", agent_name, resp.status_code)
            return None
        except Exception:  # noqa: BLE001
            logger.debug("submit_review: network error", exc_info=True)
            return None

    def list_reviews(self, agent_name: str) -> list[dict]:
        """List reviews for a public instruction."""
        try:
            resp = httpx.get(
                f"{self.base_url}/agents/{agent_name}/reviews",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("reviews", [])
            return []
        except Exception:  # noqa: BLE001
            return []

    def review_summary(self, agent_name: str) -> dict | None:
        """Get aggregated review summary for a public instruction."""
        try:
            resp = httpx.get(
                f"{self.base_url}/agents/{agent_name}/reviews/summary",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:  # noqa: BLE001
            return None

    # -- knowledge: threads ----------------------------------------------------

    def search_threads(
        self,
        *,
        q: str | None = None,
        thread_type: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search knowledge threads."""
        try:
            params: dict = {"limit": limit}
            if q:
                params["q"] = q
            if thread_type:
                params["type"] = thread_type
            if category:
                params["category"] = category
            if status:
                params["status"] = status
            resp = httpx.get(
                f"{self.base_url}/threads",
                params=params,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("threads", [])
            return []
        except Exception:  # noqa: BLE001
            return []

    def get_thread(self, thread_id: str) -> dict | None:
        """Get full thread detail with messages."""
        try:
            resp = httpx.get(
                f"{self.base_url}/threads/{thread_id}",
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:  # noqa: BLE001
            return None

    def start_thread(
        self,
        *,
        title: str,
        goal: str,
        thread_type: str,
        first_message: str,
        category: str | None = None,
        first_message_type: str = "comment",
        author_agent: str = "",
        author_repo: str = "",
    ) -> dict | None:
        """Create a new knowledge thread. Returns thread detail or None."""
        try:
            payload: dict = {
                "title": title,
                "goal": goal,
                "type": thread_type,
                "first_message": first_message,
                "first_message_type": first_message_type,
                "author_agent": author_agent,
                "author_repo": author_repo,
            }
            if category:
                payload["category"] = category
            resp = httpx.post(
                f"{self.base_url}/threads",
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            logger.debug("start_thread: HTTP %s", resp.status_code)
            return None
        except Exception:  # noqa: BLE001
            logger.debug("start_thread: network error", exc_info=True)
            return None

    def post_to_thread(
        self,
        thread_id: str,
        *,
        content: str,
        message_type: str = "comment",
        author_agent: str = "",
        author_repo: str = "",
    ) -> dict | None:
        """Post a message to an existing thread."""
        try:
            payload: dict = {
                "content": content,
                "message_type": message_type,
                "author_agent": author_agent,
                "author_repo": author_repo,
            }
            resp = httpx.post(
                f"{self.base_url}/threads/{thread_id}/messages",
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            logger.debug("post_to_thread: HTTP %s", resp.status_code)
            return None
        except Exception:  # noqa: BLE001
            logger.debug("post_to_thread: network error", exc_info=True)
            return None

    def resolve_thread(
        self, thread_id: str, *, conclusion: str,
    ) -> dict | None:
        """Set conclusion and mark thread resolved."""
        try:
            resp = httpx.put(
                f"{self.base_url}/threads/{thread_id}/conclusion",
                json={"conclusion": conclusion},
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:  # noqa: BLE001
            logger.debug("resolve_thread: network error", exc_info=True)
            return None
