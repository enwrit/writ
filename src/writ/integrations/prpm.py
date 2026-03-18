"""Install agent configs from PRPM registry (7,500+ packages).

Uses the PRPM registry HTTP API when available, with CLI subprocess fallback.
"""

from __future__ import annotations

import json
import subprocess

from writ.core.models import InstructionConfig
from writ.utils import slugify

PRPM_API_BASE = "https://registry.prpm.dev/api/v1"
_TIMEOUT = 5.0


def _search_http(query: str) -> list[dict]:
    """Search via PRPM registry HTTP API."""
    import httpx

    resp = httpx.get(
        f"{PRPM_API_BASE}/search",
        params={"q": query, "limit": 20},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("packages", [])


def _search_cli(query: str) -> list[dict]:
    """Fallback: search via prpm CLI."""
    try:
        result = subprocess.run(
            ["prpm", "search", query, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            json.JSONDecodeError):
        pass
    return []


def _install_http(package: str) -> dict | None:
    """Fetch package detail via PRPM registry HTTP API."""
    import httpx

    resp = httpx.get(
        f"{PRPM_API_BASE}/packages/{package}",
        timeout=_TIMEOUT,
    )
    if resp.status_code == 200:
        return resp.json()
    return None


def _install_cli(package: str) -> dict | None:
    """Fallback: fetch package via prpm CLI."""
    try:
        result = subprocess.run(
            ["prpm", "show", package, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            json.JSONDecodeError):
        pass
    return None


class PRPMIntegration:
    """Interface to PRPM: HTTP API first, CLI fallback."""

    def search(self, query: str) -> list[dict]:
        """Search the PRPM registry."""
        results = _search_http(query)
        if results:
            return results
        return _search_cli(query)

    def install(self, package: str) -> InstructionConfig | None:
        """Install a package from PRPM and convert to InstructionConfig."""
        pkg_info = _install_http(package)
        if pkg_info is None:
            pkg_info = _install_cli(package)
        if pkg_info is None:
            return None

        content = (
            pkg_info.get("snippet")
            or pkg_info.get("full_content")
            or pkg_info.get("content", "")
        )
        return InstructionConfig(
            name=slugify(pkg_info.get("name", package)),
            description=pkg_info.get("description", ""),
            instructions=content,
            tags=pkg_info.get("tags", []),
            version=pkg_info.get("version", "1.0.0"),
            author=pkg_info.get("author", "prpm"),
        )
