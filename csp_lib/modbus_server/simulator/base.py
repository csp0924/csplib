# =============== Modbus Server - Base Device Simulator ===============
#
# 所有設備模擬器的抽象基類

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from csp_lib.core import get_logger

from ..config import SimulatedDeviceConfig
from ..register_block import RegisterBlock

logger = get_logger("csp_lib.modbus_server.simulator")


class BaseDeviceSimulator(ABC):
    """
    設備模擬器抽象基類

    提供 register block 管理、值操作、寫入回調等共用邏輯。
    子類只需實作 update() 和選擇性覆寫 on_write()。
    """

    def __init__(self, config: SimulatedDeviceConfig) -> None:
        self._config = config
        self._register_block = RegisterBlock()
        self._values: dict[str, Any] = {}

        # 註冊所有 points 並設定初始值
        self._register_block.register_points(config.points)
        for point in config.points:
            self._values[point.name] = point.initial_value

    @property
    def device_id(self) -> str:
        return self._config.device_id

    @property
    def unit_id(self) -> int:
        return self._config.unit_id

    @property
    def config(self) -> SimulatedDeviceConfig:
        return self._config

    @property
    def register_block(self) -> RegisterBlock:
        return self._register_block

    def set_value(self, name: str, value: Any) -> None:
        """設定 point 的值（同步更新 _values 和 register_block）"""
        self._values[name] = value
        self._register_block.set_value(name, value)

    def get_value(self, name: str) -> Any:
        """取得 point 的值"""
        return self._values.get(name)

    def on_write(self, name: str, old_value: Any, new_value: Any) -> None:
        """
        Client 寫入回調（子類可覆寫）

        當 client 透過 Modbus 寫入 register 時，由 SimulatorDataBlock 呼叫。

        Args:
            name: 被寫入的 point 名稱
            old_value: 舊值
            new_value: 新值
        """
        self._values[name] = new_value

    @abstractmethod
    async def update(self) -> None:
        """
        模擬更新（子類實作）

        由 SimulationServer 的 tick loop 定期呼叫。
        """

    def reset(self) -> None:
        """重置到初始狀態"""
        for point in self._config.points:
            self._values[point.name] = point.initial_value
            self._register_block.set_value(point.name, point.initial_value)


__all__ = ["BaseDeviceSimulator"]
