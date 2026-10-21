import subprocess
from pathlib import Path

from check_wiki import MAX_PAGE_LINES, check_files, check_range, wiki_page_lines


def test_src_change_without_wiki_fails():
    errors = check_files(["src/matchmind/config.py"], page_lines={})
    assert errors == ["code changed without a wiki/ update: src/matchmind/config.py"]


def test_src_change_with_wiki_passes():
    assert check_files(["src/matchmind/config.py", "wiki/changelog.md"], page_lines={}) == []


def test_web_src_change_without_wiki_fails():
    assert check_files(["web/src/App.tsx"], page_lines={}) != []


def test_non_code_change_passes_without_wiki():
    assert check_files(["docs/realism.md", "tests/test_config.py"], page_lines={}) == []


def test_page_over_limit_fails():
    errors = check_files([], page_lines={"wiki/engine.md": MAX_PAGE_LINES + 1})
    assert errors == [f"wiki/engine.md has {MAX_PAGE_LINES + 1} lines (max {MAX_PAGE_LINES})"]


def test_page_at_limit_passes():
    assert check_files([], page_lines={"wiki/engine.md": MAX_PAGE_LINES}) == []


def test_wiki_page_lines_counts_markdown_pages(tmp_path: Path):
    (tmp_path / "a.md").write_text("one\ntwo\n")
    (tmp_path / "notes.txt").write_text("ignored\n")
    assert wiki_page_lines(tmp_path) == {"wiki/a.md": 2}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_check_range_flags_only_the_offending_commit(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("x\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    (tmp_path / "src").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "src" / "a.py").write_text("a = 1\n")
    (tmp_path / "wiki" / "README.md").write_text("map\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "good")

    (tmp_path / "src" / "a.py").write_text("a = 2\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "bad")
    bad = _git(tmp_path, "rev-parse", "--short", "HEAD")

    errors = check_range(f"{base}..HEAD", repo=tmp_path)
    assert errors == [f"{bad}: code changed without a wiki/ update: src/a.py"]
