"""Install agent configs from PRPM registry (7,500+ packages)."""

from __future__ import annotations

import json
import subprocess

from writ.core.models import AgentConfig
from writ.utils import slugify


class PRPMIntegration:
    """Interface to the PRPM CLI for installing agent packages."""

    def search(self, query: str) -> list[dict]:
        """Search the PRPM registry."""
        try:
            result = subprocess.run(
                ["prpm", "search", query, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return []

    def install(self, package: str) -> AgentConfig | None:
        """Install a package from PRPM and convert to AgentConfig."""
        try:
            result = subprocess.run(
                ["prpm", "show", package, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None

            pkg_info = json.loads(result.stdout)
            return AgentConfig(
                name=slugify(pkg_info.get("name", package)),
                description=pkg_info.get("description", ""),
                instructions=pkg_info.get("content", ""),
                tags=pkg_info.get("tags", []),
                version=pkg_info.get("version", "1.0.0"),
                author=pkg_info.get("author", "prpm"),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
