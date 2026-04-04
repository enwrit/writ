"""Install agent configs from a URL (YAML file or markdown, e.g. raw GitHub)."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
import yaml
from pydantic import ValidationError

from writ.core.models import InstructionConfig
from writ.core.scanner import _IMPORTABLE_EXTENSIONS, parse_markdown_content
from writ.utils import slugify


class URLIntegration:
    """Install agent configs from URLs."""

    def install(self, url: str, *, name_override: str | None = None) -> InstructionConfig | None:
        """Fetch a file from a URL and convert to InstructionConfig.

        Supports:
        - YAML instruction configs (dict with ``name`` + InstructionConfig fields)
        - Markdown / ``.mdc`` / text rules (parsed like ``writ add --file``)
        - GitHub blob URLs (auto-converted to raw)

        *name_override* sets the default instruction name when parsing markdown (frontmatter
        ``name`` still wins). When omitted, the filename stem from the URL is used.
        """
        raw_url = _to_raw_url(url)

        try:
            response = httpx.get(raw_url, timeout=30, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        content = response.text
        final_url = str(response.url)

        # Try parsing as YAML agent config
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "name" in data:
                cfg = InstructionConfig(**data)
                if not cfg.source:
                    cfg.source = final_url
                return cfg
        except (yaml.YAMLError, TypeError, ValueError, ValidationError):
            pass

        ext = _extension_from_url(final_url)
        initial_name = (
            name_override if name_override is not None else _name_from_url(final_url)
        )
        cfg = parse_markdown_content(content, initial_name, ext_hint=ext)
        if cfg is not None:
            if not cfg.source:
                cfg.source = final_url
            return cfg

        # Last resort: whole response body as instructions (empty parse body, etc.)
        final_name = (
            slugify(name_override) if name_override else _name_from_url(final_url)
        )
        return InstructionConfig(
            name=final_name,
            description=f"Imported from {final_url}",
            instructions=content,
            tags=["imported", "url"],
            source=final_url,
        )


def _to_raw_url(url: str) -> str:
    """Convert GitHub blob URLs to raw URLs."""
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return url


def _extension_from_url(url: str) -> str:
    """Map URL path suffix to a parse hint; default to markdown."""
    path = PurePosixPath(urlparse(url).path)
    ext = path.suffix.lower()
    if ext in _IMPORTABLE_EXTENSIONS:
        return ext
    return ".md"


def _name_from_url(url: str) -> str:
    """Extract a reasonable slug name from a URL path."""
    path = PurePosixPath(urlparse(url.split("?")[0]).path)
    stem = path.stem
    return slugify(stem) if stem else "imported-agent"
