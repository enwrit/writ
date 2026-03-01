"""Peer repository management -- read/write ``peers.yaml``.

Peers are repos that this project can communicate with via ``writ chat``.
Each peer has a transport (local or remote), auto-respond policy, and
context-sharing allowlist.
"""

from __future__ import annotations

from pathlib import Path

from writ.core.models import AutoRespondTier, PeerConfig, PeersManifest
from writ.utils import ensure_dir, project_writ_dir, yaml_dump, yaml_load


def peers_path() -> Path:
    return project_writ_dir() / "peers.yaml"


def load_peers() -> PeersManifest:
    """Load peers.yaml, returning an empty manifest if absent."""
    path = peers_path()
    if not path.is_file():
        return PeersManifest()
    raw = yaml_load(path)
    peers_raw = raw.get("peers", {})
    peers: dict[str, PeerConfig] = {}
    for name, data in peers_raw.items():
        if isinstance(data, dict):
            peers[name] = PeerConfig(name=name, **data)
    return PeersManifest(peers=peers)


def save_peers(manifest: PeersManifest) -> None:
    """Write peers.yaml."""
    data: dict = {"peers": {}}
    for name, peer in manifest.peers.items():
        entry: dict = {}
        if peer.path:
            entry["path"] = peer.path
        if peer.remote:
            entry["remote"] = peer.remote
        entry["transport"] = peer.transport
        entry["auto_respond"] = peer.auto_respond.value
        entry["max_turns"] = peer.max_turns
        if peer.allowed_context:
            entry["allowed_context"] = peer.allowed_context
        data["peers"][name] = entry
    ensure_dir(peers_path().parent)
    yaml_dump(peers_path(), data)


def add_peer(
    name: str,
    *,
    path: str | None = None,
    remote: str | None = None,
    auto_respond: AutoRespondTier = AutoRespondTier.OFF,
    max_turns: int = 10,
) -> PeerConfig:
    """Register a new peer repository."""
    manifest = load_peers()
    transport = "remote" if remote else "local"
    peer = PeerConfig(
        name=name,
        path=path,
        remote=remote,
        transport=transport,
        auto_respond=auto_respond,
        max_turns=max_turns,
    )
    manifest.peers[name] = peer
    save_peers(manifest)
    return peer


def remove_peer(name: str) -> bool:
    """Remove a peer by name. Returns True if it existed."""
    manifest = load_peers()
    if name not in manifest.peers:
        return False
    del manifest.peers[name]
    save_peers(manifest)
    return True


def get_peer(name: str) -> PeerConfig | None:
    """Look up a peer by name."""
    manifest = load_peers()
    return manifest.peers.get(name)


def resolve_peer_conversations_dir(peer: PeerConfig) -> Path | None:
    """Return the .writ/conversations/ path inside a local peer's repo.

    Returns None for remote peers (they use the backend relay).
    """
    if peer.transport == "local" and peer.path:
        p = Path(peer.path) / ".writ" / "conversations"
        if p.parent.is_dir():
            return p
    return None
