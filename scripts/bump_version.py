#!/usr/bin/env python3
"""Version bump automation script.

Usage:
    python scripts/bump_version.py 0.5.0 --dry-run  # Preview changes
    python scripts/bump_version.py 0.5.0             # Apply changes
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

# (file_relative_path, regex_pattern, replacement_template)
# {v} = new version, {date} = today's date (YYYY-MM-DD)
REPLACEMENTS: list[tuple[str, str, str]] = [
    ("csp_lib/__init__.py", r'__version__\s*=\s*"[^"]+"', '__version__ = "{v}"'),
    ("README.md", r"version-[\d.]+-green", "version-{v}-green"),
    ("README.md", r"version = \{[\d.]+\}", "version = {{{v}}}"),
    ("README.md", r"目前版本：`[\d.]+`", "目前版本：`{v}`"),
    ("CITATION.cff", r"^version:\s*[\d.]+", "version: {v}"),
    ("CITATION.cff", r'^date-released:\s*"[^"]+"', 'date-released: "{date}"'),
    ("NOTICE", r"\(Version\s+[\d.]+\)", "(Version {v})"),
    ("docs/Home.md", r"(目前版本\*?\*?[：:]\s*)[\d.]+", r"\g<1>{v}"),
]

CHANGELOG_PATH = "CHANGELOG.md"


def validate_version(version: str) -> bool:
    return bool(re.match(r"^\d+\.\d+\.\d+$", version))


def get_current_version() -> str:
    init_file = ROOT / "csp_lib" / "__init__.py"
    content = init_file.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if not m:
        print("ERROR: Cannot find __version__ in csp_lib/__init__.py")
        sys.exit(1)
    return m.group(1)


def bump_file(filepath: Path, pattern: str, replacement: str, dry_run: bool) -> int:
    """Replace pattern in file. Returns number of replacements made."""
    if not filepath.exists():
        print(f"  SKIP (not found): {filepath}")
        return 0

    content = filepath.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

    if count == 0:
        return 0

    if dry_run:
        # Show what would change
        for line_no, (old_line, new_line) in enumerate(
            zip(content.splitlines(), new_content.splitlines(), strict=False), 1
        ):
            if old_line != new_line:
                print(f"  L{line_no}: {old_line.strip()}")
                print(f"     -> {new_line.strip()}")
    else:
        filepath.write_text(new_content, encoding="utf-8")

    return count


def bump_changelog(version: str, date: str, dry_run: bool) -> bool:
    """Insert new version header below [Unreleased] in CHANGELOG.md."""
    changelog = ROOT / CHANGELOG_PATH
    if not changelog.exists():
        print(f"  SKIP (not found): {changelog}")
        return False

    content = changelog.read_text(encoding="utf-8")
    pattern = r"^(## \[Unreleased\]\s*\n)"
    replacement = f"## [Unreleased]\n\n## [{version}] - {date}\n"

    new_content, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)

    if count == 0:
        print("  WARNING: Could not find '## [Unreleased]' in CHANGELOG.md")
        return False

    if dry_run:
        print(f"  Insert: ## [{version}] - {date}")
    else:
        changelog.write_text(new_content, encoding="utf-8")

    return True


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Bump version across all files")
    parser.add_argument("version", help="New version (e.g. 0.5.0)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    new_version = args.version
    dry_run = args.dry_run

    if not validate_version(new_version):
        print(f"ERROR: Invalid version format: {new_version} (expected X.Y.Z)")
        sys.exit(1)

    old_version = get_current_version()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    mode = "DRY RUN" if dry_run else "APPLYING"
    print(f"[{mode}] {old_version} -> {new_version} (date: {today})")
    print()

    errors = []

    for rel_path, pattern, template in REPLACEMENTS:
        filepath = ROOT / rel_path
        replacement = template.format(v=new_version, date=today)
        print(f"  {rel_path}:")
        count = bump_file(filepath, pattern, replacement, dry_run)
        if count == 0 and filepath.exists():
            errors.append(f"No match in {rel_path} for pattern: {pattern}")
            print("    ERROR: pattern not found")
        else:
            print(f"    {count} replacement(s)")

    print(f"\n  {CHANGELOG_PATH}:")
    if not bump_changelog(new_version, today, dry_run):
        errors.append("CHANGELOG.md update failed")

    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"\nDone! {'(dry run — no files modified)' if dry_run else 'All files updated.'}")


if __name__ == "__main__":
    main()
