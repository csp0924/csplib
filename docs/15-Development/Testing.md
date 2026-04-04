---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# 測試指南

## 執行測試

### 執行所有測試

```bash
uv run pytest tests/ -v
```

### 執行單一測試檔案

```bash
uv run pytest tests/equipment/test_core_point.py
```

### 依模式匹配執行

```bash
uv run pytest -k "test_scale_transform"
```

---

## 平行測試

專案已啟用 **pytest-xdist**，預設以 `-n auto --dist loadfile` 平行執行測試，可大幅加速。

若需暫時關閉平行：

```bash
uv run pytest tests/ -v -n 0
```

---

## 非同步測試

專案已設定 `asyncio_mode = "auto"`，**不需要** `@pytest.mark.asyncio` 裝飾器。所有 `async def test_*` 函式會自動以非同步模式執行。

```python
async def test_device_read():
    async with device:
        values = await device.read_all()
        assert "voltage" in values
```

---

## 測試結構

測試檔案位於 `tests/` 目錄，結構與原始碼對應：

```
tests/
├── controller/         # Controller 模組測試
│   ├── system/         # 系統管理測試
│   ├── test_core.py
│   ├── test_executor.py
│   └── test_strategies.py
├── core/               # Core 模組測試
├── equipment/          # Equipment 模組測試
│   ├── test_alarm_*.py
│   ├── test_core_*.py
│   ├── test_device_*.py
│   └── test_transport_*.py
├── integration/        # Integration 模組測試
├── manager/            # Manager 模組測試
├── modbus/             # Modbus 模組測試
├── modbus_gateway/     # Modbus Gateway 模組測試（v0.6.0）
├── modbus_server/      # Modbus Server 模組測試（v0.5.2）
├── mongo/              # MongoDB 模組測試
├── redis/              # Redis 模組測試
├── statistics/         # Statistics 模組測試（v0.6.0）
└── gui/                # GUI 模組測試（v0.5.2）
```

---

## 相關頁面

- [[Dev Setup]] - 開發環境設定
- [[Linting]] - Linting 與格式化
- [[CI-CD Pipeline]] - CI/CD 流程
