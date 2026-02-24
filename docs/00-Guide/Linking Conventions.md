---
tags: [type/guide, status/complete]
---
# Linking Conventions

> 連結規範

## 基本規則

- 所有內部連結使用 `[[wiki link]]` 格式（shortest path）
- 不使用 Markdown 連結格式 `[text](url)`（外部 URL 除外）

## Class 頁面連結規範

每個 Class 頁面必須連結：

1. **所在模組的 MOC** — 例如 `[[_MOC Equipment]]`
2. **建構參數中的類別** — 例如 `DeviceConfig` 頁面連結 `[[ReadPoint]]`
3. **回傳值類別** — 例如 `execute()` 回傳 `[[Command]]`
4. **發射的事件** — 例如 `[[DeviceEventEmitter]]` 中的事件名稱
5. **消費的事件** — 例如 Manager 訂閱的設備事件

## MOC 頁面連結規範

每個 MOC 頁面必須連結：

1. **該區塊的所有頁面**
2. **上游模組 MOC** — 依賴的模組
3. **下游模組 MOC** — 被依賴的模組

## Reference 頁面

- 使用 Dataview 動態查詢自動生成索引
- 不手動維護連結列表

## 外部連結

- 原始碼路徑記錄在 frontmatter 的 `source` 欄位
- 外部文件連結使用 Markdown 格式：`[文件名](URL)`
