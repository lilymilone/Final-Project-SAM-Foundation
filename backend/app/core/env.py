"""Environment loading for SAM SPACE.

Precedence, highest first:
  1. Variables already set in the process environment.
  2. The repository's own .env file.
  3. The .env file one folder above the repository. That is where the teaching
     staff keep theirs:  submissions/.env  +  submissions/sam-space/

python-dotenv never overrides a variable that is already set. So loading the repo
file first and the parent file second gives exactly this order, and the parent
file only fills in values that are still missing. Paths are built from this
file's location, never from the working directory. Only labels ("repo",
"parent") are reported, never values.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# backend/app/core/env.py -> parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]


def env_file_candidates(repo_root: Path = REPO_ROOT) -> list[tuple[str, Path]]:
    return [("repo", repo_root / ".env"), ("parent", repo_root.parent / ".env")]


def load_environment(repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    """Load .env files in precedence order. Returns which ones were found."""
    loaded: list[str] = []
    for label, path in env_file_candidates(repo_root):
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(label)
    return tuple(loaded)
