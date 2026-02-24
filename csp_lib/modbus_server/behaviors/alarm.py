# =============== Modbus Server - Alarm Behavior ===============
#
# 告警行為：支援 auto/manual/latched reset 模式

from __future__ import annotations

from ..config import AlarmResetMode


class AlarmBehavior:
    """
    告警行為管理器

    管理單個 alarm bit 的觸發與重置邏輯。

    Attributes:
        alarm_code: 告警代碼
        bit_position: 在 alarm register 中的 bit 位置
        reset_mode: 重置模式 (auto/manual/latched)
    """

    def __init__(
        self,
        alarm_code: str,
        bit_position: int,
        reset_mode: AlarmResetMode = AlarmResetMode.AUTO,
    ) -> None:
        self._alarm_code = alarm_code
        self._bit_position = bit_position
        self._reset_mode = reset_mode
        self._active = False
        self._triggered = False  # 是否曾經觸發（用於 latched 模式）

    @property
    def alarm_code(self) -> str:
        return self._alarm_code

    @property
    def bit_position(self) -> int:
        return self._bit_position

    @property
    def reset_mode(self) -> AlarmResetMode:
        return self._reset_mode

    @property
    def is_active(self) -> bool:
        return self._active

    def update(self, trigger_condition: bool) -> bool:
        """
        更新告警狀態

        Args:
            trigger_condition: 觸發條件是否成立

        Returns:
            更新後的 active 狀態
        """
        if trigger_condition:
            self._active = True
            self._triggered = True
        elif self._reset_mode == AlarmResetMode.AUTO:
            # AUTO 模式：條件消失自動清除
            self._active = False

        # MANUAL 和 LATCHED 模式：保持 active 直到手動 reset
        return self._active

    def manual_reset(self) -> bool:
        """
        手動重置告警（MANUAL 模式用）

        Returns:
            是否成功重置
        """
        if self._reset_mode == AlarmResetMode.MANUAL and self._active:
            self._active = False
            return True
        return False

    def force_reset(self) -> bool:
        """
        強制重置告警（LATCHED 模式用）

        Returns:
            是否成功重置
        """
        if self._reset_mode == AlarmResetMode.LATCHED and self._active:
            self._active = False
            self._triggered = False
            return True
        return False

    def reset(self) -> None:
        """重置到初始狀態"""
        self._active = False
        self._triggered = False


__all__ = ["AlarmBehavior"]
