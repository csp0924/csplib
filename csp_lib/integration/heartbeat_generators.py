# =============== Integration - Heartbeat Value Generators ===============
#
# 心跳值產生器協定與內建實作
#
# 將「下一個心跳值要填什麼」這件事抽出成 Protocol，讓 HeartbeatService
# 從 v0.8.1 起可接受任意符合該協定的產生器物件，取代舊版以 HeartbeatMode
# enum 為主的「三選一硬編碼」設計。
#
# 內建產生器：
#   - ToggleGenerator     : 每個 key 在 0 / 1 之間交替
#   - IncrementGenerator  : 遞增到 ``max_value`` 後歸零
#   - ConstantGenerator   : 永遠回傳同一個常數值
#
# 設計重點：
#   - 以 ``key`` 作為多設備共用同一 generator instance 時的狀態隔離鍵；
#     如兩台 PCS 都用同一個 IncrementGenerator instance，各自獨立計數。
#   - ``reset(key=None)`` 可清除全部或指定 key 的狀態。
#   - 所有實作皆為非 async，因心跳值計算為純記憶體運算，不需 I/O。
#
# 向後相容：舊版以 HeartbeatMode enum + HeartbeatService 內部 ``_counters``
# dict 計數的路徑完全保留；新 API 走 ``HeartbeatMapping.value_generator``
# 欄位，兩條路徑不可混用（由 ``HeartbeatMapping.__post_init__`` 驗證）。

from __future__ import annotations

from typing import Protocol, runtime_checkable

from csp_lib.core import get_logger

logger = get_logger(__name__)


@runtime_checkable
class HeartbeatValueGenerator(Protocol):
    """心跳值產生器協定

    任何實作 ``next(key)`` 與 ``reset(key)`` 的物件皆可作為 HeartbeatService
    的值來源。``key`` 用於在多設備共用同一 generator instance 時保持各自的
    內部狀態。

    Methods:
        next(key): 依 key 回傳下一個心跳值（int）。
        reset(key): 清除指定 key 的狀態；``key=None`` 時清除所有狀態。
    """

    def next(self, key: str) -> int:
        """回傳指定 key 的下一個心跳值"""
        ...

    def reset(self, key: str | None = None) -> None:
        """清除 key 對應的內部狀態；``None`` 代表清除全部"""
        ...


class ToggleGenerator:
    """交替 0 / 1 的心跳值產生器

    每個 ``key`` 有獨立狀態，連續呼叫 ``next(key)`` 回傳 ``0, 1, 0, 1, ...``。
    初始狀態為 0，所以第一次呼叫 ``next`` 會回傳 1（與舊版
    ``HeartbeatMode.TOGGLE`` 的計算方式一致：``1 - current``）。
    """

    def __init__(self) -> None:
        # 各 key 最近一次回傳的值
        self._state: dict[str, int] = {}

    def next(self, key: str) -> int:
        """回傳 key 的下一個 toggle 值（0 / 1 交替）"""
        current = self._state.get(key, 0)
        next_val = 1 - current
        self._state[key] = next_val
        return next_val

    def reset(self, key: str | None = None) -> None:
        """清除狀態；``key=None`` 代表清除全部 key"""
        if key is None:
            self._state.clear()
        else:
            self._state.pop(key, None)


class IncrementGenerator:
    """遞增計數的心跳值產生器

    每個 ``key`` 獨立計數，到達 ``max_value`` 後歸零（``(n + 1) % (max_value + 1)``）。
    適合設備端以序號檢測「是否收到新心跳」的場景。

    Args:
        max_value: 計數最大值；到達後歸零。合法範圍 ``1 <= max_value <= 65535``。

    Raises:
        ValueError: ``max_value`` 超出合法範圍。
    """

    def __init__(self, max_value: int = 65535) -> None:
        if not (1 <= max_value <= 65535):
            raise ValueError(f"IncrementGenerator: max_value must be in [1, 65535], got {max_value}")
        self._max_value = max_value
        # 各 key 最近一次回傳的值
        self._state: dict[str, int] = {}

    def next(self, key: str) -> int:
        """回傳 key 的下一個遞增值（到 max_value 後歸零）"""
        current = self._state.get(key, 0)
        next_val = (current + 1) % (self._max_value + 1)
        self._state[key] = next_val
        return next_val

    def reset(self, key: str | None = None) -> None:
        """清除狀態；``key=None`` 代表清除全部 key"""
        if key is None:
            self._state.clear()
        else:
            self._state.pop(key, None)


class ConstantGenerator:
    """常數值心跳值產生器

    任何 ``next(key)`` 呼叫皆回傳 ``value``。``reset`` 為 no-op（無狀態）。

    Args:
        value: 固定寫入值；合法範圍 ``0 <= value <= 65535``（Modbus 16-bit register 上界）。

    Raises:
        ValueError: ``value`` 超出合法範圍。
    """

    def __init__(self, value: int = 1) -> None:
        if not (0 <= value <= 65535):
            raise ValueError(f"ConstantGenerator: value must be in [0, 65535], got {value}")
        self._value = value

    def next(self, key: str) -> int:
        """回傳固定值（與 key 無關）"""
        return self._value

    def reset(self, key: str | None = None) -> None:
        """無狀態，no-op（保留方法以符合 Protocol）"""


__all__ = [
    "ConstantGenerator",
    "HeartbeatValueGenerator",
    "IncrementGenerator",
    "ToggleGenerator",
]
