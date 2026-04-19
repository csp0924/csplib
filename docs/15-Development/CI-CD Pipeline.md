---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
updated: 2026-04-20
---

# CI/CD Pipeline

專案使用 GitHub Actions 進行持續整合與發佈，搭配 release-please 自動維護版本與 CHANGELOG。

---

## 流程概覽

```
PR (Pull Request)                       ← gating（必須綠燈才能 merge）
  ├── Lint (Ruff + format + mypy)
  ├── Test on ubuntu-latest      ┐
  ├── Test on windows-latest     ├── pytest 全套（3 OS matrix）
  ├── Test on macos-latest       ┘
  └── Build Check（dry-run sdist + wheel + import）

push main                                ← 精簡 smoke（~30s）
  ├── Lint only
  └── release-please:
       ├── 更新 Release PR（計算下版本 + CHANGELOG）
       └── 若 Release PR 已 merge → 推 vX.Y.Z tag

Tag vX.Y.Z (release-please 自動推)       ← 發版前最後驗證 + publish
  ├── Preflight（tag vs __version__ 一致性）
  ├── Test on 3 OS                      ← gating，failed 則 publish 不跑
  ├── Build dist
  ├── Extract release notes
  ├── Publish to PyPI（environment: pypi，需人工 approve）
  └── Create GitHub Release
```

---

## 為何 push main 不重跑 test

| 觀察 | 結論 |
|------|------|
| PR 必須 up-to-date with main 才能 merge | PR CI 跑的就是合進 main 後的內容 |
| Release PR 只改 `CHANGELOG.md` + `__version__` | 沒 source 變動，重跑 test 沒意義 |
| 真正的安全網在 `release.yml` 的 test job | publish 前再跑一次 3 OS，有任何漂移會擋住 |
| macOS + Windows + Ubuntu test ~6 分鐘/次 | 每次 push main 省這個時間，月省可觀 CI quota |

`lint` 仍在 push main 跑，用來擋 parallel merge race 後的格式衝突。

---

## PR 流程

| 步驟 | 平台 | 說明 |
|------|------|------|
| Lint | Ubuntu | Ruff check + Ruff format check + mypy |
| Test | Ubuntu + Windows + macOS | pytest 全套 + coverage（threshold 80% 在 ubuntu）|
| Build Check | Ubuntu | 建 sdist + wheel + 驗 pure-Python + 安裝 + import |
| Commitlint | Ubuntu | 強制 conventional commit + scope 白名單 |

`pull_request_template.md` 必填項目參考 `CLAUDE.md` 中 Git rules 章節。

---

## Tag 發佈流程

當 release-please 推 `vX.Y.Z` tag 後，`release.yml` 自動接手：

### 1. Preflight

驗證 tag 版本與 `csp_lib/__init__.py` 的 `__version__` 一致。
RC tag (`v1.0.0-rc1`) 允許 `__version__=1.0.0`（base version match）。

### 2. Test (3 OS matrix)

跟 PR 階段相同的 pytest 全套，在 ubuntu/windows/macOS 上跑。
**這是 publish 前最後一道驗證**，任何 fail 都會擋住下游 job。

### 3. Build

建 pure Python sdist + wheel（`py3-none-any`），所有平台通用。

### 4. Publish to PyPI

- 走 `environment: pypi`（需在 GitHub repo Settings → Environments 設 Required reviewers）
- 用 OIDC trusted publishing + attestations，不需 PyPI token secret
- RC tag 改走 TestPyPI（dry run）

```bash
pip install csp0924_lib          # 從 PyPI 安裝
pip install csp0924_lib[all]     # 安裝所有功能
```

### 5. Create GitHub Release

用 `gh release create` 一次建 release + 附 wheel/sdist asset
（避開 GitHub Immutable Releases 的「先 create 再 upload」陷阱，
詳見 `bug_lessons/ci_release_please_pitfalls.md`）。

---

## 失敗恢復

`release.yml` 的任何 job fail 都不會把已破的版本「半推半就發出去」。
完整恢復 SOP 見 [[Release Recovery]]。

關鍵原則：**PyPI 版本號 immutable**。preflight/test/build/notes fail 沒燒版本號，
推 fix commit 讓 release-please 自動 bump 下個 patch 即可。

---

## 工作流程檔案

| 檔案 | 觸發 | 用途 |
|------|------|------|
| `.github/workflows/ci.yml` | PR + push main | gating + smoke |
| `.github/workflows/commitlint.yml` | PR + push main | conventional commit + scope 檢查 |
| `.github/workflows/release-please.yml` | push main | 維護 Release PR + 推 tag |
| `.github/workflows/release.yml` | tag `vX.Y.Z` push | test + build + publish |

---

## 本地模擬 CI

```bash
# Lint
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy csp_lib/

# Test
uv run pytest tests/ -v

# Build
python -m build
```

或一鍵跑全部：使用 `/check` skill。

---

## 相關頁面

- [[Dev Setup]] — 開發環境設定
- [[Testing]] — 測試指南
- [[Linting]] — Linting 與格式化
- [[Release Recovery]] — release.yml 失敗恢復 SOP
