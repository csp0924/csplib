---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
---

# CI/CD Pipeline

專案使用 GitHub Actions 進行持續整合與發佈。

---

## 流程概覽

```
PR (Pull Request)
  └── Lint + Test（Ubuntu + Windows）

Tag (v*)
  └── Lint + Test
       └── Build Wheels（Windows / manylinux）
            └── Publish to PyPI
```

---

## PR 流程

當開啟 Pull Request 時，自動執行：

| 步驟 | 平台 | 說明 |
|------|------|------|
| Lint | Ubuntu + Windows | Ruff check |
| Test | Ubuntu + Windows | pytest 全套測試 |

### 測試環境設定

在測試環境中，設定 `SKIP_CYTHON=1` 跳過 Cython 編譯：

```yaml
env:
  SKIP_CYTHON: 1
```

---

## Tag 發佈流程

當推送符合 `v*` 格式的 tag 時（例如 `v0.3.3`），自動執行完整發佈流程：

### 1. Lint + Test

與 PR 流程相同，在 Ubuntu 與 Windows 上執行 lint 與測試。

### 2. Build Wheels

在多平台建置 Cython 編譯的 wheel：

| 平台 | 產出 |
|------|------|
| Windows x64 | `csp_lib-*-cp313-cp313-win_amd64.whl` |
| manylinux x64 | `csp_lib-*-cp313-cp313-manylinux_*.whl` |

### 3. Publish to PyPI

使用 trusted publishing + attestations 發佈到 PyPI。

```bash
pip install csp0924_lib          # 從 PyPI 安裝
pip install csp0924_lib[all]     # 安裝所有功能
```

---

## 工作流程檔案

CI/CD 設定位於 `.github/workflows/build-wheels.yml`。

---

## 本地模擬 CI

在本地模擬 CI 檢查流程：

```bash
# Lint
uv run ruff check .

# Test
SKIP_CYTHON=1 uv run pytest tests/ -v

# Build
python build_wheel.py
```

---

## 相關頁面

- [[Dev Setup]] - 開發環境設定
- [[Testing]] - 測試指南
- [[Linting]] - Linting 與格式化
- [[Cython Build]] - Cython 建置
- [[Version History]] - 版本歷史
