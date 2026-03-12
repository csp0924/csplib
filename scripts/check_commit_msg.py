#!/usr/bin/env python3
"""Check commit message follows conventional commit format.

Used as a pre-commit hook (commit-msg stage).
Reads the commit message file path from sys.argv[1].

Format: <type>(<scope>): <description>
  - type: feat|fix|docs|style|refactor|test|ci|chore|perf|build|revert
  - scope: optional, in parentheses
  - description: 1-72 chars total for first line
"""

import re
import sys

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|test|ci|chore|perf|build|revert)"
    r"(\(.+\))?"
    r": "
    r".{1,}"
    r"$"
)

MAX_LENGTH = 72

ALLOWED_TYPES = [
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "test",
    "ci",
    "chore",
    "perf",
    "build",
    "revert",
]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check_commit_msg.py <commit-msg-file>")
        return 1

    msg_file = sys.argv[1]
    with open(msg_file, encoding="utf-8") as f:
        lines = f.readlines()

    # Skip empty lines and comments
    first_line = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            first_line = stripped
            break

    if not first_line:
        print("ERROR: Empty commit message")
        return 1

    # Auto-pass merge commits and reverts
    if first_line.startswith("Merge ") or first_line.startswith("Revert "):
        return 0

    if len(first_line) > MAX_LENGTH:
        print(f"ERROR: First line is {len(first_line)} chars (max {MAX_LENGTH})")
        print(f"  > {first_line}")
        return 1

    if not PATTERN.match(first_line):
        print("ERROR: Commit message does not follow conventional format")
        print(f"  > {first_line}")
        print("  Expected: <type>(<scope>): <description>")
        print(f"  Types: {', '.join(ALLOWED_TYPES)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
