"""Install agent configs from Agent Skills (agentskill.sh, 100K+ skills).

Uses the agentskill.sh HTTP API when available, with CLI subprocess fallback.
"""

from __future__ import annotations

import json
import subprocess

from writ.core.models import InstructionConfig
from writ.utils import slugify

SKILLS_API_BASE = "https://agentskill.sh/api/agent"
HTTP_TIMEOUT = 5.0


def _search_http(query: str) -> list[dict]:
    """Search Agent Skills registry via HTTP API."""
    import httpx

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.get(
                f"{SKILLS_API_BASE}/search",
                params={"q": query, "limit": 50},
            )
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, httpx.TimeoutException, json.JSONDecodeError):
        return []

    results = data.get("results", [])
    return [
        {
            "name": s.get("name", "?"),
            "slug": s.get("slug", ""),
            "owner": s.get("owner", ""),
            "description": s.get("description", ""),
            "tags": (
                s.get("skillTypes", [])
                or ([s.get("category", "")] if s.get("category") else [])
            ),
        }
        for s in results
    ]


def _install_http(skill_name: str) -> InstructionConfig | None:
    """Fetch skill from Agent Skills registry via HTTP API.

    skill_name can be:
    - Full slug: owner/name (e.g. josecortezz25/typescript)
    - Short name: we search first and use the first match's slug
    """
    import httpx

    slug = skill_name
    owner = ""

    if "/" not in skill_name:
        # Search to resolve short name to slug
        results = _search_http(skill_name)
        if not results:
            return None
        first = results[0]
        slug = first.get("slug", "")
        owner = first.get("owner", "")
        if not slug:
            return None
    else:
        parts = skill_name.split("/", 1)
        owner = parts[0]
        # slug is owner/name
        slug = skill_name

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.get(
                f"{SKILLS_API_BASE}/skills/{slug}/install",
                params={"owner": owner} if owner else {},
            )
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, httpx.TimeoutException, json.JSONDecodeError):
        return None

    skill_md = data.get("skillMd", "")
    if not skill_md:
        return None

    return InstructionConfig(
        name=slugify(data.get("name", skill_name)),
        description=data.get("description", ""),
        instructions=skill_md,
        tags=data.get("capabilities", []) or data.get("skillTypes", []) or [],
        version="1.0.0",
        author=data.get("owner", "agent-skills"),
    )


def _search_cli(query: str) -> list[dict]:
    """Search Agent Skills registry via CLI."""
    try:
        result = subprocess.run(
            ["agent-skills", "search", query, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return []


def _install_cli(skill_name: str) -> InstructionConfig | None:
    """Install a skill via CLI."""
    try:
        result = subprocess.run(
            ["agent-skills", "show", skill_name, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        skill_info = json.loads(result.stdout)
        return InstructionConfig(
            name=slugify(skill_info.get("name", skill_name)),
            description=skill_info.get("description", ""),
            instructions=skill_info.get("content", ""),
            tags=skill_info.get("tags", []),
            version=skill_info.get("version", "1.0.0"),
            author=skill_info.get("author", "agent-skills"),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


class SkillsIntegration:
    """Interface to Agent Skills (HTTP API with CLI fallback)."""

    def search(self, query: str) -> list[dict]:
        """Search Agent Skills registry. Tries HTTP first, falls back to CLI."""
        results = _search_http(query)
        if results:
            return results
        raw = _search_cli(query)
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict) and "results" in raw:
            return raw["results"]
        return []

    def install(self, skill_name: str) -> InstructionConfig | None:
        """Install a skill. Tries HTTP first, falls back to CLI."""
        cfg = _install_http(skill_name)
        if cfg is not None:
            return cfg
        return _install_cli(skill_name)
