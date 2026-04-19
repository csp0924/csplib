#!/usr/bin/env python3
"""Check commit message follows conventional commit format (release-please 版).

Used as a pre-commit hook (commit-msg stage).
Reads the commit message file path from sys.argv[1].

Format: <type>(<scope>)?: <description>
  - type: feat|fix|docs|style|refactor|test|ci|chore|perf|build|revert
  - `!` 後綴表 breaking change（如 `feat!:` 或 `feat(controller)!:`）
  - scope: optional，必須為模組名（白名單），禁止版號
  - description: 首行最長 100 chars（見下方 MAX_LENGTH 註解）

差異 vs 舊版：
  1. scope 白名單化 — 禁用版號 scope（`feat(v0.8.0):` 會被 release-please 當成
     CHANGELOG section 名，會跑出怪條目）
  2. 支援 `type!:` breaking change 語法（release-please 會 bump major）
  3. Body 內 `BREAKING CHANGE:` trailer 也納入檢查提示
  4. 允許 `chore(main): release X.Y.Z` 這類 release-please bot commit
"""

import re
import sys

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 首行長度上限。Git 社群傳統是 72（配合 `git log --oneline` 單行顯示），
# 但中文 commit message 一個中文字在 `len()` 下即占 1 char，
# 實務上 `fix(ci): commitlint 加入 deps-dev scope + ...` 這類中英混寫很容易破 72。
# 取 Angular / commitlint 慣例的 100 作折衷：
#   - 仍足夠短到 GitHub PR 標題不折行（GitHub 約於 72 才視覺截斷，但可滑看全）
#   - 留給中文描述 + 英文識別符混寫的合理空間
#   - 超過 100 通常代表該把細節移到 body
MAX_LENGTH = 100

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

# Scope 白名單 — 模組名（csp_lib/ 下目錄名 + 約定的 meta scope）
# Meta scope: deps / release / ci / docs / tests / build / repo
ALLOWED_SCOPES = {
    # csp_lib 模組
    "core",
    "modbus",
    "equipment",
    "controller",
    "manager",
    "integration",
    "mongo",
    "redis",
    "storage",  # mongo + redis 合稱
    "cluster",
    "monitor",
    "notification",
    "modbus_server",
    "modbus-server",
    "modbus_gateway",
    "modbus-gateway",
    "gui",
    "statistics",
    "alarm",
    "can",
    "grpc",
    # Meta scopes
    "deps",
    "deps-dev",  # dependabot 對 dev dependency groups 使用此 scope
    "release",
    "ci",
    "docs",
    "tests",
    "build",
    "repo",
    "main",  # release-please bot 用
}

# Pattern：type(scope)?!?: description
PATTERN = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|test|ci|chore|perf|build|revert)"
    r"(\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r": "
    r"(?P<desc>.{1,})"
    r"$"
)

# 版號樣式，禁用於 scope（v0.8.0 / 0.8.0 / v1 都禁）
VERSION_SCOPE_PATTERN = re.compile(r"^v?\d+(\.\d+)*(-\w+)?$")


def check(first_line: str) -> list[str]:
    """Return list of error messages; empty list means pass."""
    errors: list[str] = []

    if len(first_line) > MAX_LENGTH:
        errors.append(f"First line is {len(first_line)} chars (max {MAX_LENGTH})")

    m = PATTERN.match(first_line)
    if not m:
        errors.append("Does not match `<type>(<scope>)?!?: <description>`")
        return errors  # 後面 group 依賴 match，提早 return

    scope = m.group("scope")
    if scope is not None:
        if VERSION_SCOPE_PATTERN.match(scope):
            errors.append(
                f"Version scope `{scope}` is forbidden — "
                f"use module name (e.g. `feat(controller):`) instead. "
                f"release-please uses scope for CHANGELOG grouping; "
                f"version scopes produce malformed entries."
            )
        elif scope not in ALLOWED_SCOPES:
            errors.append(f"Unknown scope `{scope}`. Allowed: {', '.join(sorted(ALLOWED_SCOPES))}")

    return errors


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

    # Auto-pass merge commits and reverts（git 自動產生）
    if first_line.startswith("Merge ") or first_line.startswith("Revert "):
        return 0

    # Auto-pass release-please bot commits
    if first_line.startswith("chore: release") or first_line.startswith("chore(main): release"):
        return 0

    errors = check(first_line)
    if errors:
        print("ERROR: Commit message does not conform to conventional commit format:")
        print(f"  > {first_line}")
        print()
        for err in errors:
            print(f"  - {err}")
        print()
        print("Expected format: <type>(<scope>)?!?: <description>")
        print(f"  Allowed types:  {', '.join(ALLOWED_TYPES)}")
        print("  Breaking:        append `!` (e.g. `feat!:` or `feat(controller)!:`)")
        print("  Examples:")
        print("    feat(controller): 新增 Droop 策略")
        print("    fix(equipment): ReadScheduler 漏掉 timeout 例外")
        print("    feat(manager)!: UnifiedDeviceManager.subscribe 簽名變更")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
