"""Install agent configs from Agent Skills CLI (175K+ skills)."""

from __future__ import annotations

import json
import subprocess

from writ.core.models import AgentConfig
from writ.utils import slugify


class SkillsIntegration:
    """Interface to Agent Skills CLI."""

    def search(self, query: str) -> list[dict]:
        """Search Agent Skills CLI registry."""
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

    def install(self, skill_name: str) -> AgentConfig | None:
        """Install a skill and convert to AgentConfig."""
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
            return AgentConfig(
                name=slugify(skill_info.get("name", skill_name)),
                description=skill_info.get("description", ""),
                instructions=skill_info.get("content", ""),
                tags=skill_info.get("tags", []),
                version=skill_info.get("version", "1.0.0"),
                author=skill_info.get("author", "agent-skills"),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
