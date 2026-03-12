---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
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

## 非同步測試

使用 `@pytest.mark.asyncio` 裝飾器標記非同步測試（專案未設定全域 asyncio 模式）。

```python
import pytest

@pytest.mark.asyncio
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
├── mongo/              # MongoDB 模組測試
└── redis/              # Redis 模組測試
```

---

## 相關頁面

- [[Dev Setup]] - 開發環境設定
- [[Linting]] - Linting 與格式化
- [[CI-CD Pipeline]] - CI/CD 流程
