---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# CI/CD Pipeline

專案使用 GitHub Actions 進行持續整合與發佈。

---

## 流程概覽

```
PR (Pull Request)
  ├── Lint (Ruff + mypy)
  ├── Test（Ubuntu + Windows）
  └── Changelog Check（非 dependabot PR 必須更新 CHANGELOG.md）

Tag (v*)
  └── Lint + Test
       └── Build sdist + wheel
            └── Publish to PyPI（含版本檢查 + release notes）
```

---

## PR 流程

當開啟 Pull Request 時，自動執行：

| 步驟 | 平台 | 說明 |
|------|------|------|
| Lint | Ubuntu | Ruff check + Ruff format check + mypy |
| Test | Ubuntu + Windows | pytest 全套測試 |
| Changelog Check | Ubuntu | 確認 CHANGELOG.md 已更新（可加 `skip-changelog` label 跳過） |

---

## Tag 發佈流程

當推送符合 `v*` 格式的 tag 時（例如 `v0.6.0`），自動執行完整發佈流程：

### 1. Lint + Test

與 PR 流程相同，在 Ubuntu 與 Windows 上執行 lint 與測試。

### 2. Build

建置 pure Python sdist 與 wheel（`py3-none-any`），所有平台通用。

### 3. Publish to PyPI

使用 trusted publishing + attestations 發佈到 PyPI。

```bash
pip install csp0924_lib          # 從 PyPI 安裝
pip install csp0924_lib[all]     # 安裝所有功能
```

---

## 工作流程檔案

CI/CD 設定位於 `.github/workflows/build-wheels.yml`。

主要使用工具：
- `astral-sh/setup-uv@v7` — 安裝 uv
- `uv sync --group dev` — 安裝開發依賴
- `uv run ruff check .` — Lint 檢查
- `uv run ruff format --check .` — 格式檢查
- `uv run mypy csp_lib/` — 型別檢查

---

## 本地模擬 CI

在本地模擬 CI 檢查流程：

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

---

## 相關頁面

- [[Dev Setup]] - 開發環境設定
- [[Testing]] - 測試指南
- [[Linting]] - Linting 與格式化
- [[Version History]] - 版本歷史
