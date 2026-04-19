<!--
提示：PR title 會在 squash merge 後變成 main 上那個 commit 的 message 首行，
所以 title 必須符合 conventional commit 格式（否則 commitlint 會擋）：
  <type>(<scope>)?!?: <description>   (首行 ≤ 100 chars；中文字算 1 char)

type: feat | fix | perf | refactor | revert | docs | style | test | ci | chore | build
scope: 模組名（見 CLAUDE.md 白名單）— 禁用版號 scope（如 v0.8.0）
!:    breaking change，或在 body 加 `BREAKING CHANGE: <說明>` trailer

dependabot / release-please 開的 PR 會自動跳過 commitlint，不用改 title。
-->

## 變更摘要

<!-- 1~3 句話說明「為什麼」做這個改動。「做了什麼」請看 commit / diff。 -->

## 變更類型

- [ ] `feat` — 新功能（release-please 會 **minor bump**）
- [ ] `fix` — Bug 修復（**patch bump**）
- [ ] `perf` — 效能改善（**patch bump**）
- [ ] `refactor` — 重構（**patch bump**，不得改 public API）
- [ ] `revert` — 回退（**patch bump**）
- [ ] `docs` / `style` / `test` / `ci` / `chore` / `build` — 不 bump
- [ ] **Breaking change**（**major bump**）— commit 含 `!` 或 body 有 `BREAKING CHANGE:` trailer

## 影響範圍

<!--
- 哪些模組 / 層被動到？
- 公開 API 是否有 signature / exception / 回傳語義 變動？
- 是否影響 CI / 部署 / 發佈流程？
- 是否動到 optional dependencies？
-->

## 測試

<!-- 列出實際跑過的 command 與場景（不是「預計要跑」）。 -->

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy csp_lib/`
- [ ] `uv run python -m pytest tests/ -v`
- [ ] 新增 / 修改的行為有對應測試（bug fix 需 Test-First failing test）

## Checklist

- [ ] Commit message 符合 conventional commit 格式（首行 ≤ 100 chars，scope 在白名單內）
- [ ] Branch 名為 `<type>/<short-desc>`，且 type 與 commit type 對應
- [ ] **未**手動修改 `CHANGELOG.md` / `csp_lib/__init__.py::__version__` / git tag（release-please 接管）
- [ ] 若為 breaking change，已明確標註 `!` 或 `BREAKING CHANGE:` trailer，並在「變更摘要」說明遷移方式
- [ ] 若新增 / 移除 optional dependency，`pyproject.toml` 的 extras 已同步更新

## 相關 Issue / PR

<!-- Closes #123 / Related #456 / Depends on #789 -->
