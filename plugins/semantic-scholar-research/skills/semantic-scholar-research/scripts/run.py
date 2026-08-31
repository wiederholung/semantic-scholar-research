from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _find_plugin_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src" / "semantic_scholar_agent"
        ).is_dir():
            return candidate
    raise RuntimeError("Could not locate the semantic-scholar-research plugin root")


REPO_ROOT = _find_plugin_root()
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


if __name__ == "__main__":
    cli = importlib.import_module("semantic_scholar_agent.cli")
    raise SystemExit(cli.main())
