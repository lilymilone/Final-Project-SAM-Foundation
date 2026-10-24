"""The .env lookup the teaching staff rely on: process env > repo .env > parent .env."""

from __future__ import annotations

import os

from backend.app.core.config import Settings
from backend.app.core.env import load_environment

VARS = ("SAMTEST_SHARED", "SAMTEST_PARENT_ONLY", "SAMTEST_REPO_ONLY", "SAMTEST_PROCESS")


def _layout(tmp_path, repo_lines=None, parent_lines=None):
    submissions = tmp_path / "submissions"
    repo = submissions / "sam-space"
    repo.mkdir(parents=True)
    if parent_lines is not None:
        (submissions / ".env").write_text("\n".join(parent_lines) + "\n")
    if repo_lines is not None:
        (repo / ".env").write_text("\n".join(repo_lines) + "\n")
    return repo


def test_precedence_process_then_repo_then_parent(tmp_path, monkeypatch):
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("SAMTEST_PROCESS", "from-process")
    repo = _layout(
        tmp_path,
        repo_lines=["SAMTEST_SHARED=from-repo", "SAMTEST_REPO_ONLY=repo", "SAMTEST_PROCESS=repo-should-lose"],
        parent_lines=["SAMTEST_SHARED=from-parent", "SAMTEST_PARENT_ONLY=parent", "SAMTEST_PROCESS=parent-should-lose"],
    )
    loaded = load_environment(repo)
    assert loaded == ("repo", "parent")
    assert os.environ["SAMTEST_PROCESS"] == "from-process"
    assert os.environ["SAMTEST_SHARED"] == "from-repo"
    assert os.environ["SAMTEST_REPO_ONLY"] == "repo"
    assert os.environ["SAMTEST_PARENT_ONLY"] == "parent"


def test_parent_env_alone_is_enough(tmp_path, monkeypatch):
    """Teaching-staff layout: no .env in the repo, keys one folder up."""
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    repo = _layout(tmp_path, parent_lines=["SAMTEST_PARENT_ONLY=found-it"])
    assert load_environment(repo) == ("parent",)
    assert os.environ["SAMTEST_PARENT_ONLY"] == "found-it"


def test_no_env_files_is_not_an_error(tmp_path):
    repo = _layout(tmp_path)
    assert load_environment(repo) == ()


def test_keys_never_appear_in_settings_repr():
    s = Settings(openai_api_key="fake-secret-value-123", portkey_api_key="fake-secret-value-456")
    assert "fake-secret-value-123" not in repr(s)
    assert "fake-secret-value-456" not in repr(s)


def test_provider_resolution():
    assert Settings(openai_api_key="a", portkey_api_key="b").provider == "openai"
    assert Settings(portkey_api_key="b").provider == "portkey"
    assert Settings(openai_api_key="a", portkey_api_key="b", ai_provider_setting="portkey").provider == "portkey"
    assert Settings(ai_provider_setting="openai", portkey_api_key="b").provider is None
    assert Settings().provider is None
