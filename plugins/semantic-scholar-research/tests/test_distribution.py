from __future__ import annotations

import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifests_share_identity_and_version() -> None:
    codex = _json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    claude = _json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
    assert codex["name"] == claude["name"] == "semantic-scholar-research"
    assert codex["version"] == claude["version"] == "0.1.0"
    assert codex["license"] == claude["license"] == "MIT"


def test_marketplaces_point_to_the_bundled_plugin() -> None:
    codex = _json(REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json")
    claude = _json(REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json")
    assert codex["name"] == claude["name"] == "wiederholung-semantic-scholar"
    assert codex["plugins"][0]["source"]["path"] == "./plugins/semantic-scholar-research"
    assert claude["plugins"][0]["source"] == "./plugins/semantic-scholar-research"
