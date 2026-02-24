---
tags: [type/concept, status/complete]
---
# Async Patterns

> csp_lib 非同步優先模式與生命週期管理

## 非同步優先設計

csp_lib 的所有設備 I/O 和管理器操作均基於 Python `asyncio`。這項設計決策的核心原因：

1. **Modbus 通訊為 I/O 密集** — 設備讀寫涉及網路延遲，async 可在等待回應時處理其他任務
2. **多設備並行** — 一個系統可能同時管理數十台設備，async 避免了執行緒開銷
3. **事件處理不阻塞** — 事件發射與處理在背景進行，不影響主讀取循環

## AsyncLifecycleMixin

[[AsyncLifecycleMixin]] 是所有長生命週期物件的基底 Mixin，定義於 `csp_lib.core.lifecycle`。

### 設計（Template Method 模式）

```python
class AsyncLifecycleMixin:
    async def start(self) -> None:
        """啟動服務"""
        await self._on_start()

    async def stop(self) -> None:
        """停止服務"""
        await self._on_stop()

    async def _on_start(self) -> None:
        """子類別覆寫此方法以實作啟動邏輯"""

    async def _on_stop(self) -> None:
        """子類別覆寫此方法以實作停止邏輯"""

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.stop()
```

### 使用方式

子類只需覆寫 `_on_start()` 和 `_on_stop()` 鉤子：

```python
class MyService(AsyncLifecycleMixin):
    async def _on_start(self) -> None:
        # 初始化資源、建立連線
        ...

    async def _on_stop(self) -> None:
        # 釋放資源、關閉連線
        ...
```

### Async Context Manager

所有繼承 [[AsyncLifecycleMixin]] 的類別都支援 `async with` 語法，確保資源自動清理：

```python
async with MyService() as svc:
    # 服務已啟動
    await svc.do_something()
# 離開 context 時自動呼叫 stop()
```

### 使用此 Mixin 的類別

| 類別 | 模組 | 說明 |
|------|------|------|
| [[DeviceManager]] | Manager | 設備生命週期管理 |
| [[GridControlLoop]] | Integration | 基本控制迴圈 |
| [[SystemController]] | Integration | 完整系統控制器 |

## Async 設計模式

### 非同步客戶端

Modbus 客戶端（[[PymodbusTcpClient]]、[[PymodbusRtuClient]]、[[SharedPymodbusTcpClient]]）皆為非同步實作：

```python
async with PymodbusTcpClient(config) as client:
    result = await client.read_holding_registers(address=0, count=10)
    await client.write_register(address=100, value=500)
```

### 非同步事件處理

[[DeviceEventEmitter]] 使用 `asyncio.Queue` 作為事件緩衝區，避免同步回呼阻塞讀取循環。詳見 [[Event System]]。

### 非阻塞 emit

```python
# emit() 為非阻塞 — 事件放入佇列後立即返回
emitter.emit("value_change", payload)

# emit_await() 為阻塞 — 等待所有 handler 處理完成
await emitter.emit_await("alarm_triggered", payload)
```

### 執行緒卸載

[[ComputeOffloader]] 將 CPU 密集的計算卸載到執行緒池，避免阻塞事件循環：

```python
offloader = ComputeOffloader()
result = await offloader.run(heavy_computation, arg1, arg2)
```

### RTU 共線鎖

RTU 通訊為半雙工，同一串口在同一時間只能有一個請求。[[PymodbusRtuClient]] 使用 `asyncio.Lock` 確保請求序列化：

```python
async with self._lock:
    result = await self._client.read_holding_registers(...)
```

### 批次上傳

[[DataUploadManager]] 和 [[MongoBatchUploader]] 使用內部佇列收集資料，定時批次寫入 MongoDB，減少資料庫壓力。

## 測試非同步程式碼

使用 `@pytest.mark.asyncio` 裝飾器標記非同步測試：

```python
@pytest.mark.asyncio
async def test_device_lifecycle():
    async with AsyncModbusDevice(config) as device:
        assert device.is_connected
```

## 相關頁面

- [[AsyncLifecycleMixin]] — 生命週期 Mixin 類別頁面
- [[Event System]] — 非同步事件系統
- [[Layered Architecture]] — 各層的 async 角色
- [[_MOC Core]] — Core 模組（lifecycle.py 所在）
- [[_MOC Architecture]] — 返回架構索引
