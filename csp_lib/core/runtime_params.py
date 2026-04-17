"""
RuntimeParameters — Thread-safe 即時參數容器

提供跨執行緒 / 跨 asyncio task 安全的參數讀寫，用於：
- ProtectionRule 讀取動態 SOC 上下限、功率限制
- ModbusGatewayServer WriteHook 寫入 EMS 指令
- ContextBuilder 注入 context.extra
- 任何需要從外部系統即時更新的參數

使用 threading.Lock 確保 Modbus thread (modbus_tk hook) 與
asyncio event loop 之間的安全存取。

Usage::

    params = RuntimeParameters(
        soc_max=95.0,
        soc_min=5.0,
        grid_limit_pct=100,
    )

    # 讀取
    soc_max = params.get("soc_max")

    # 寫入（觸發 observers）
    params.set("soc_max", 90.0)

    # 批次更新
    params.update({"soc_max": 90.0, "soc_min": 10.0})

    # 原子性快照
    snap = params.snapshot()

    # 變更通知
    params.on_change(lambda key, old, new: print(f"{key}: {old} → {new}"))
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from loguru import logger as _root_logger

logger = _root_logger.bind(module="csp_lib.core.runtime_params")

# observer 簽名: (key, old_value, new_value) -> None
ChangeCallback = Callable[[str, Any, Any], None]


class RuntimeParameters:
    """
    Thread-safe 的即時參數容器

    所有讀寫操作透過 threading.Lock 保護，確保：
    - asyncio task 之間的一致性
    - Modbus hook thread 與 asyncio event loop 之間的安全存取

    Attribute-style 存取：
        除 ``get()`` / ``set()`` 之外，也支援屬性語法：

            params.soc_max = 90.0        # 等同 params.set("soc_max", 90.0)
            value = params.soc_max       # 等同 params.get("soc_max")，缺失時 AttributeError

        方便與 StrategyContext.params 搭配撰寫策略程式碼。

    Warning:
        **Subclassing 注意**：若於 subclass 定義與參數同名的 **class attribute**
        （例如 ``class MyParams(RuntimeParameters): soc_max = 100``），
        attribute-style 讀取會優先命中 class attribute 而非 ``_values``，
        造成與 ``get()`` 不一致的行為。建議 subclass 不要覆蓋參數名稱；
        若確實需要類別預設值，請於 ``__init__`` 傳入 ``initial_values``。

    Attributes:
        _values: 參數鍵值對
        _lock: 保護 _values 的鎖
        _observers: 變更通知回呼列表
    """

    __slots__ = ("_values", "_lock", "_observers")

    def __init__(self, **initial_values: Any) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, Any] = dict(initial_values)
        self._observers: list[ChangeCallback] = []

    # ─────────────────────── 讀取 ───────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """取得參數值，不存在時回傳 default"""
        with self._lock:
            return self._values.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        """回傳所有參數的原子性淺拷貝"""
        with self._lock:
            return dict(self._values)

    def keys(self) -> list[str]:
        """回傳所有參數 key"""
        with self._lock:
            return list(self._values.keys())

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._values

    def __len__(self) -> int:
        with self._lock:
            return len(self._values)

    # ─────────────────────── 寫入 ───────────────────────

    def set(self, key: str, value: Any) -> None:
        """設定單一參數值，值變更時觸發 observers"""
        with self._lock:
            old = self._values.get(key)
            self._values[key] = value
        if old != value:
            self._notify(key, old, value)

    def update(self, mapping: dict[str, Any]) -> None:
        """批次更新多個參數，值變更時觸發 observers"""
        changes: list[tuple[str, Any, Any]] = []
        with self._lock:
            for key, value in mapping.items():
                old = self._values.get(key)
                self._values[key] = value
                if old != value:
                    changes.append((key, old, value))
        for key, old, new in changes:
            self._notify(key, old, new)

    def setdefault(self, key: str, default: Any) -> Any:
        """若 key 不存在則設定為 default 並回傳，存在則直接回傳"""
        with self._lock:
            if key not in self._values:
                self._values[key] = default
                return default
            return self._values[key]

    def delete(self, key: str) -> None:
        """刪除參數，不存在時靜默忽略"""
        with self._lock:
            old = self._values.pop(key, None)
        if old is not None:
            self._notify(key, old, None)

    # ─────────────────────── 觀察者 ───────────────────────

    def on_change(self, callback: ChangeCallback) -> None:
        """
        註冊變更通知回呼

        回呼簽名: callback(key: str, old_value: Any, new_value: Any) -> None
        回呼在 set/update/delete 時同步呼叫（在鎖外），
        若需要 async 操作，請在回呼內使用 loop.call_soon_threadsafe()。
        """
        self._observers.append(callback)

    def remove_observer(self, callback: ChangeCallback) -> None:
        """移除已註冊的變更通知回呼"""
        try:
            self._observers.remove(callback)
        except ValueError:
            pass

    def _notify(self, key: str, old: Any, new: Any) -> None:
        """通知所有觀察者，單一觀察者例外不影響其他"""
        for cb in self._observers:
            try:
                cb(key, old, new)
            except Exception:
                logger.opt(exception=True).warning(f"RuntimeParameters observer 執行失敗: key={key}")

    # ─────────────────────── Attribute-style 存取 ───────────────────────

    def __getattr__(self, name: str) -> Any:
        """
        Attribute-style 讀取：``params.soc_max`` 等同 ``params.get("soc_max")``，
        但缺失時拋 ``AttributeError`` 而非回傳 ``None``，確保 ``hasattr`` 行為正確。

        Note:
            ``__getattr__`` 僅在傳統屬性查找失敗後才被呼叫。
            ``__slots__`` 中的 ``_values`` / ``_lock`` / ``_observers``
            會先被找到，不會進入此分支。

        Args:
            name: 參數名稱。底線開頭視為內部屬性，一律拋 ``AttributeError``
                  以避免干擾 Python 內部機制（如 copy、pickle、IDE introspection）。

        Raises:
            AttributeError: 參數不存在，或為底線開頭的未知屬性。
        """
        if name.startswith("_"):
            raise AttributeError(name)
        with self._lock:
            if name in self._values:
                return self._values[name]
        raise AttributeError(f"{type(self).__name__!s} has no parameter '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Attribute-style 寫入：``params.soc_max = 90.0`` 等同
        ``params.set("soc_max", 90.0)``，會觸發 observers。

        底線開頭屬性走 ``object.__setattr__`` 原生路徑，
        否則 ``self._lock = ...`` 等初始化會無窮遞迴回到 ``self.set()``。

        Args:
            name: 屬性或參數名稱。
            value: 欲寫入的值。
        """
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self.set(name, value)

    # ─────────────────────── 表示 ───────────────────────

    def __repr__(self) -> str:
        with self._lock:
            keys = list(self._values.keys())
        return f"RuntimeParameters({', '.join(keys)})"


__all__ = ["RuntimeParameters", "ChangeCallback"]
