"""Conversation lifecycle, markdown read/write, and file attachment embedding.

Conversations are stored as single append-only markdown files in
``.writ/conversations/``.  Each file has YAML frontmatter and sequential
message blocks separated by ``---`` rules.

Format reference:
  ``writ-platform/.cursor/insights/2026-02-28-agent-communication-architecture.md``
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from writ.core.file_io import atomic_append, file_lock
from writ.core.models import (
    Conversation,
    ConversationStatus,
    Message,
    Participant,
)
from writ.utils import project_writ_dir, slugify

# Files that must never be attached (security blocklist).
_ATTACHMENT_BLOCKLIST_PATTERNS = (
    ".env",
    "*.key",
    "*.pem",
    "credentials.*",
    "secrets.*",
)

_ATTACHMENT_BLOCKLIST_DIRS = (
    "node_modules",
    ".git",
    "__pycache__",
)

_MAX_ATTACHMENT_SIZE = 128 * 1024  # 128 KB per file


# ---------------------------------------------------------------------------
# Conversation directory helpers
# ---------------------------------------------------------------------------

def conversations_dir() -> Path:
    return project_writ_dir() / "conversations"


def _conv_filename(peer_repo: str, topic: str) -> str:
    """Build ``{peer}--{topic-slug}.md``."""
    return f"{slugify(peer_repo)}--{slugify(topic)}.md"


def _generate_conv_id() -> str:
    return f"conv-{uuid.uuid4().hex[:12]}"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_msg_id(conv: Conversation) -> str:
    return f"msg-{len(conv.messages) + 1:03d}"


# ---------------------------------------------------------------------------
# Frontmatter serialization
# ---------------------------------------------------------------------------

def _dump_frontmatter(conv: Conversation) -> str:
    data: dict[str, Any] = {
        "format_version": conv.format_version,
        "id": conv.id,
        "participants": [
            {"agent": p.agent, "repo": p.repo, **({"device": p.device} if p.device else {})}
            for p in conv.participants
        ],
        "goal": conv.goal,
        "status": conv.status.value,
        "created": _fmt_ts(conv.created),
        "last_activity": _fmt_ts(conv.last_activity),
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True).rstrip()


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from the beginning of a markdown file."""
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


# ---------------------------------------------------------------------------
# Message serialization
# ---------------------------------------------------------------------------

def _render_message(msg: Message) -> str:
    """Render a single message as a markdown block."""
    header = f"## [{msg.id}] {msg.author_agent} . {msg.author_repo} @ {_fmt_ts(msg.timestamp)}"
    parts = [header, "", msg.content]
    if msg.attachments:
        parts.append("")
        parts.extend(msg.attachments)
    parts.append("")
    parts.append("---")
    parts.append("")
    return "\n".join(parts)


def _parse_messages(body: str) -> list[Message]:
    """Parse message blocks from the body (everything after frontmatter)."""
    pattern = re.compile(
        r"^## \[(?P<id>msg-\d+)\] (?P<agent>[^\s.]+) \. (?P<repo>\S+) @ (?P<ts>\S+)\s*$",
        re.MULTILINE,
    )
    msgs: list[Message] = []
    matches = list(pattern.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        raw = body[start:end].strip().rstrip("-").strip()

        attachments: list[str] = []
        content_lines: list[str] = []
        in_attached = False
        attached_buf: list[str] = []
        for line in raw.split("\n"):
            if line.strip().startswith("<attached "):
                in_attached = True
                attached_buf = [line]
                if "</attached>" in line:
                    attachments.append("\n".join(attached_buf))
                    in_attached = False
                    attached_buf = []
                continue
            if in_attached:
                attached_buf.append(line)
                if "</attached>" in line:
                    attachments.append("\n".join(attached_buf))
                    in_attached = False
                    attached_buf = []
                continue
            content_lines.append(line)

        try:
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC,
            )
        except ValueError:
            ts = _now_utc()

        msgs.append(Message(
            id=m.group("id"),
            author_agent=m.group("agent"),
            author_repo=m.group("repo"),
            timestamp=ts,
            content="\n".join(content_lines).strip(),
            attachments=attachments,
        ))
    return msgs


# ---------------------------------------------------------------------------
# Attachment embedding
# ---------------------------------------------------------------------------

def _is_blocked(filepath: str) -> bool:
    """Check if a filename matches the security blocklist."""
    import fnmatch

    name = Path(filepath).name.lower()
    for pat in _ATTACHMENT_BLOCKLIST_PATTERNS:
        if fnmatch.fnmatch(name, pat.lower()):
            return True
    parts = Path(filepath).parts
    for d in _ATTACHMENT_BLOCKLIST_DIRS:
        if d in parts:
            return True
    return False


def embed_files(file_paths: list[str], repo_root: Path | None = None) -> list[str]:
    """Read files and return ``<attached>`` blocks.

    Blocked files are silently skipped with a note.
    """
    root = repo_root or Path.cwd()
    blocks: list[str] = []
    for rel in file_paths:
        if _is_blocked(rel):
            blocks.append(
                f'<attached file="{rel}" blocked="true" />'
            )
            continue
        target = root / rel
        if not target.is_file():
            blocks.append(f'<attached file="{rel}" error="file not found" />')
            continue
        size = target.stat().st_size
        if size > _MAX_ATTACHMENT_SIZE:
            blocks.append(
                f'<attached file="{rel}" type="binary" size="{size}" '
                f'error="too large (max {_MAX_ATTACHMENT_SIZE})" />'
            )
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            blocks.append(f'<attached file="{rel}" type="binary" size="{size}" />')
            continue
        blocks.append(f'<attached file="{rel}">\n{content}\n</attached>')
    return blocks


def embed_context(uris: list[str]) -> list[str]:
    """Resolve ``writ://`` URIs and return ``<attached>`` blocks."""
    from writ.core import store
    from writ.utils import yaml_dumps

    blocks: list[str] = []
    for uri in uris:
        if uri.startswith("writ://instructions/"):
            name = uri.split("/", 3)[-1]
            cfg = store.load_instruction(name)
            if cfg is None:
                blocks.append(f'<attached context="{uri}" error="not found" />')
                continue
            content = yaml_dumps(cfg.model_dump(mode="json"))
            blocks.append(f'<attached context="{uri}">\n{content}\n</attached>')
        else:
            blocks.append(f'<attached context="{uri}" error="unsupported URI" />')
    return blocks


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def create_conversation(
    *,
    peer_repo: str,
    goal: str,
    local_agent: str,
    local_repo: str,
    peer_agent: str = "",
    device: str = "",
) -> Conversation:
    """Create a new conversation and write the initial file."""
    conv = Conversation(
        id=_generate_conv_id(),
        participants=[
            Participant(agent=local_agent, repo=local_repo, device=device),
            Participant(agent=peer_agent or "agent", repo=peer_repo, device=""),
        ],
        goal=goal,
        status=ConversationStatus.ACTIVE,
    )
    path = conversations_dir() / _conv_filename(peer_repo, goal)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"---\n{_dump_frontmatter(conv)}\n---\n\n"
    path.write_text(header, encoding="utf-8")
    return conv


def append_message(
    conv_path: Path,
    *,
    agent: str,
    repo: str,
    content: str,
    attach_files: list[str] | None = None,
    attach_context: list[str] | None = None,
    repo_root: Path | None = None,
) -> Message:
    """Append a message to a conversation file (locked, atomic)."""
    conv = load_conversation(conv_path)
    if conv is None:
        raise FileNotFoundError(f"Conversation file not found: {conv_path}")

    msg_id = _next_msg_id(conv)
    attachments: list[str] = []
    if attach_files:
        attachments.extend(embed_files(attach_files, repo_root))
    if attach_context:
        attachments.extend(embed_context(attach_context))

    msg = Message(
        id=msg_id,
        author_agent=agent,
        author_repo=repo,
        content=content,
        attachments=attachments,
    )

    block = _render_message(msg)
    atomic_append(conv_path, block)
    _update_frontmatter_field(conv_path, "last_activity", _fmt_ts(_now_utc()))
    return msg


def load_conversation(path: Path) -> Conversation | None:
    """Parse a conversation markdown file into a ``Conversation`` model."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    if not fm:
        return None

    body_start = text.find("---", text.find("---") + 3)
    body = text[body_start + 3:] if body_start != -1 else ""

    participants = [
        Participant(**p) for p in fm.get("participants", [])
    ]
    status_raw = fm.get("status", "active")
    try:
        status = ConversationStatus(status_raw)
    except ValueError:
        status = ConversationStatus.ACTIVE

    created_str = fm.get("created", "")
    last_str = fm.get("last_activity", "")
    try:
        created = datetime.strptime(created_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC,
        )
    except (ValueError, TypeError):
        created = _now_utc()
    try:
        last_activity = datetime.strptime(last_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC,
        )
    except (ValueError, TypeError):
        last_activity = created

    messages = _parse_messages(body)

    return Conversation(
        format_version=fm.get("format_version", 1),
        id=fm.get("id", ""),
        participants=participants,
        goal=fm.get("goal", ""),
        status=status,
        created=created,
        last_activity=last_activity,
        messages=messages,
        turn_count=len(messages),
    )


def list_conversations() -> list[tuple[Path, Conversation]]:
    """Return all conversations in ``.writ/conversations/``."""
    cdir = conversations_dir()
    if not cdir.is_dir():
        return []
    results: list[tuple[Path, Conversation]] = []
    for p in sorted(cdir.glob("*.md")):
        conv = load_conversation(p)
        if conv is not None:
            results.append((p, conv))
    return results


def find_conversation(conv_id: str) -> tuple[Path, Conversation] | None:
    """Find a conversation by its ID."""
    for path, conv in list_conversations():
        if conv.id == conv_id:
            return path, conv
    return None


def update_status(path: Path, status: ConversationStatus) -> None:
    """Update the status field in a conversation's frontmatter."""
    _update_frontmatter_field(path, "status", status.value)


def complete_conversation(path: Path, summary: str) -> None:
    """Mark a conversation as completed and append a summary message."""
    update_status(path, ConversationStatus.COMPLETED)
    content = f"**Conversation completed.** Summary: {summary}"
    atomic_append(path, f"\n{content}\n")


# ---------------------------------------------------------------------------
# Frontmatter patching (in-place update of a single field)
# ---------------------------------------------------------------------------

def _update_frontmatter_field(path: Path, key: str, value: str) -> None:
    """Update a single field in the YAML frontmatter of a conversation file."""
    with file_lock(path):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not match:
            return
        fm_text = match.group(1)
        pattern = re.compile(rf"^({re.escape(key)}:\s*)(.*)$", re.MULTILINE)
        if pattern.search(fm_text):
            new_fm = pattern.sub(rf"\g<1>{value}", fm_text)
        else:
            new_fm = fm_text + f"\n{key}: {value}"
        new_text = f"---\n{new_fm}\n---{text[match.end():]}"
        path.write_text(new_text, encoding="utf-8")
