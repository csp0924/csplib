---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
---

# Linting 與格式化

## 工具

專案使用 **Ruff** 進行 linting 與格式化，**mypy** 進行靜態型別檢查。

---

## Ruff 指令

### 檢查 Lint

```bash
uv run ruff check .
```

### 自動修復

```bash
uv run ruff check --fix .
```

### 格式化

```bash
uv run ruff format .
```

---

## Mypy 型別檢查

```bash
uv run mypy csp_lib/
```

---

## 程式碼風格規範

| 項目 | 規範 |
|------|------|
| 行長度 | 120 字元 |
| 引號 | 雙引號 (`"`) |
| 目標 Python 版本 | 3.13 |

### Ruff 規則

| 規則集 | 說明 |
|--------|------|
| `E` | pycodestyle errors |
| `W` | pycodestyle warnings |
| `F` | pyflakes |
| `I` | isort（import 排序） |
| `B` | flake8-bugbear |

### 忽略的規則

| 規則 | 原因 |
|------|------|
| `E501` | 由 formatter 處理行長度 |
| `B027` | 允許空的 abstract methods（設計意圖） |

---

## 相關頁面

- [[Dev Setup]] - 開發環境設定
- [[Testing]] - 測試指南
