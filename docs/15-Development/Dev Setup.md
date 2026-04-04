---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# 開發環境設定

## 系統需求

- **Python 3.13+**（專案使用 Python 3.13 作為目標版本）
- **uv**：推薦的 Python 套件管理工具

---

## 安裝步驟

### 1. 安裝所有依賴（含開發依賴）

```bash
uv sync --all-groups --all-extras
```

此指令會安裝所有 optional dependencies 及開發工具（pytest, ruff, mypy 等）。

### 2. 可編輯安裝

```bash
pip install -e .
```

---

## Optional Dependencies

套件支援按需安裝：

```bash
pip install csp0924_lib[modbus]     # Modbus 通訊 (pymodbus)
pip install csp0924_lib[mongo]      # MongoDB (motor)
pip install csp0924_lib[redis]      # Redis (redis-py)
pip install csp0924_lib[monitor]    # 系統監控 (psutil)
pip install csp0924_lib[cluster]    # 分散式叢集 (etcd)
pip install csp0924_lib[gui]        # Web GUI (FastAPI + uvicorn)
pip install csp0924_lib[all]        # 所有功能
```

---

## 開發工具

| 工具 | 用途 |
|------|------|
| `pytest` | 測試框架（含 pytest-xdist 平行測試、pytest-asyncio 非同步支援） |
| `ruff` | Linting 與格式化 |
| `mypy` | 靜態型別檢查 |
| `pre-commit` | Git hook 自動執行 `ruff --fix` 與 `ruff-format` |

---

## Pre-commit Hooks

專案已設定 pre-commit hooks，自動在 commit 前執行：

- `ruff check --fix` — 自動修復 lint 問題
- `ruff format` — 自動格式化
- Commit message 格式檢查（`<type>(<scope>): <description>`）

---

## 相關頁面

- [[Testing]] - 測試指南
- [[Linting]] - Linting 與格式化
