"""Install agent configs from a URL (YAML file or git repo)."""

from __future__ import annotations

import httpx
import yaml

from writ.core.models import AgentConfig
from writ.utils import slugify


class URLIntegration:
    """Install agent configs from URLs."""

    def install(self, url: str) -> AgentConfig | None:
        """Fetch a YAML file from a URL and convert to AgentConfig.

        Supports:
        - Direct YAML file URLs
        - Raw GitHub file URLs
        - GitHub blob URLs (auto-converted to raw)
        """
        raw_url = _to_raw_url(url)

        try:
            response = httpx.get(raw_url, timeout=30, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        content = response.text

        # Try parsing as YAML agent config
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "name" in data:
                return AgentConfig(**data)
        except (yaml.YAMLError, ValueError):
            pass

        # If not valid YAML config, treat content as raw instructions
        name = _name_from_url(url)
        return AgentConfig(
            name=name,
            description=f"Imported from {url}",
            instructions=content,
            tags=["imported", "url"],
        )


def _to_raw_url(url: str) -> str:
    """Convert GitHub blob URLs to raw URLs."""
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return url


def _name_from_url(url: str) -> str:
    """Extract a reasonable name from a URL."""
    from pathlib import PurePosixPath

    path = PurePosixPath(url.split("?")[0])
    stem = path.stem
    return slugify(stem) if stem else "imported-agent"
