# =============== Equipment Device - Mixins ===============
#
# 責任拆分 Mixin
#
# AlarmMixin: 告警管理（is_protected, active_alarms, clear_alarm, _evaluate_alarm）
# WriteMixin: 寫入管理（write, execute_action, available_actions）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.equipment.alarm import AlarmEventType, AlarmState
from csp_lib.equipment.transport import WriteResult, WriteStatus

from .events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_WRITE_COMPLETE,
    EVENT_WRITE_ERROR,
    DeviceAlarmPayload,
    WriteCompletePayload,
    WriteErrorPayload,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from csp_lib.equipment.alarm import AlarmEvaluator, AlarmStateManager
    from csp_lib.equipment.core import WritePoint
    from csp_lib.equipment.transport import ValidatedWriter

    from .config import DeviceConfig
    from .events import DeviceEventEmitter


class AlarmMixin:
    """
    告警管理 mixin

    提供 is_protected, active_alarms, clear_alarm, _evaluate_alarm。

    依賴：self._alarm_manager, self._alarm_evaluators, self._emitter, self._config
    """

    if TYPE_CHECKING:
        _alarm_manager: AlarmStateManager
        _config: DeviceConfig
        _emitter: DeviceEventEmitter
        _alarm_evaluators: list[AlarmEvaluator]
        _disabled_points: set[str]

    @property
    def is_protected(self) -> bool:
        """設備是否已保護"""
        return self._alarm_manager.has_protection_alarm()

    @property
    def active_alarms(self) -> list[AlarmState]:
        """啟用中的告警"""
        return self._alarm_manager.get_active_alarms()

    async def clear_alarm(self, code: str) -> None:
        """手動清除告警"""
        event = self._alarm_manager.clear_alarm(code)
        if event:
            payload = DeviceAlarmPayload(device_id=self._config.device_id, alarm_event=event)
            await self._emitter.emit_await(EVENT_ALARM_CLEARED, payload)

    async def _evaluate_alarm(self, values: dict[str, Any]) -> None:
        """評估告警（跳過 disabled 點位）"""
        for evaluator in self._alarm_evaluators:
            if evaluator.point_name in self._disabled_points:
                continue
            point_value = values.get(evaluator.point_name)
            if point_value is None:
                continue

            evaluations = evaluator.evaluate(point_value)
            events = self._alarm_manager.update(evaluations)

            for event in events:
                payload = DeviceAlarmPayload(device_id=self._config.device_id, alarm_event=event)
                if event.event_type == AlarmEventType.TRIGGERED:
                    await self._emitter.emit_await(EVENT_ALARM_TRIGGERED, payload)
                else:
                    await self._emitter.emit_await(EVENT_ALARM_CLEARED, payload)


class WriteMixin:
    """
    寫入管理 mixin

    提供 write, execute_action, available_actions。

    依賴：self._write_points, self._writer, self._emitter, self._config, self.ACTIONS
    """

    if TYPE_CHECKING:
        _config: DeviceConfig
        _emitter: DeviceEventEmitter
        _write_points: dict[str, WritePoint]
        _writer: ValidatedWriter
        _disabled_points: set[str]
        ACTIONS: dict[str, str]

    async def write(self, name: str, value: Any, verify: bool = False) -> WriteResult:
        """寫入點位值"""
        device_id = getattr(self._config, "device_id", "?")
        logger.debug(f"[{device_id}] write 開始: point={name}, value={value}, verify={verify}")

        # 檢查點位是否被停用
        if name in self._disabled_points:
            logger.warning(f"[{device_id}] write 點位已停用: {name}")
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=name,
                value=value,
                error_message=f"點位 '{name}' 已停用",
            )

        point = self._write_points.get(name)
        if point is None:
            logger.warning(f"[{device_id}] write 點位不存在: {name}, 可用點位: {list(self._write_points.keys())}")
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=name,
                value=value,
                error_message=f"寫入點位 {name} 失敗，點位不存在",
            )

        logger.debug(f"[{device_id}] write 點位已找到: {name}, address={point.address}, fc={point.function_code}")
        result = await self._writer.write(point=point, value=value, verify=verify)
        logger.debug(
            f"[{device_id}] write 結果: point={name}, status={result.status.value}, error={result.error_message or 'none'}"
        )

        if result.status == WriteStatus.SUCCESS:
            self._emitter.emit(
                EVENT_WRITE_COMPLETE,
                WriteCompletePayload(device_id=self._config.device_id, point_name=name, value=value),
            )
        else:
            self._emitter.emit(
                EVENT_WRITE_ERROR,
                WriteErrorPayload(
                    device_id=self._config.device_id, point_name=name, value=value, error=result.error_message
                ),
            )

        return result

    async def execute_action(self, action: str, **params: Any) -> WriteResult:
        """
        執行高階動作

        根據 ACTIONS 映射呼叫對應的方法。

        Args:
            action: 動作名稱（如 "start", "stop"）
            **params: 傳遞給方法的參數

        Returns:
            WriteResult：成功時 status=SUCCESS，失敗時包含錯誤訊息

        Raises:
            不拋出異常，所有錯誤透過 WriteResult 回傳
        """
        device_id = getattr(self._config, "device_id", "?")
        logger.debug(f"[{device_id}] execute_action 開始: action={action}, params={params}")

        method_name = self.ACTIONS.get(action)
        if method_name is None:
            logger.warning(f"[{device_id}] action 不支援: {action}, 可用: {list(self.ACTIONS.keys())}")
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=action,
                value=None,
                error_message=f"Action '{action}' not supported. Available: {list(self.ACTIONS.keys())}",
            )

        method = getattr(self, method_name, None)
        if method is None or not callable(method):
            logger.error(f"[{device_id}] action 方法不存在: action={action} → method={method_name}")
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=action,
                value=None,
                error_message=f"Method '{method_name}' not found for action '{action}'",
            )

        try:
            logger.debug(f"[{device_id}] 呼叫方法: {method_name}(**{params})")
            result = await method(**params)

            # 若方法回傳 WriteResult，直接使用其狀態
            if isinstance(result, WriteResult):
                if result.status != WriteStatus.SUCCESS:
                    logger.error(
                        f"[{device_id}] execute_action 失敗: action={action}, status={result.status.value}, error={result.error_message}"
                    )
                else:
                    logger.info(f"[{device_id}] execute_action 成功: action={action}")
                return result

            logger.info(f"[{device_id}] execute_action 成功: action={action}")
            return WriteResult(
                status=WriteStatus.SUCCESS,
                point_name=action,
                value=params if params else None,
            )
        except Exception as e:
            logger.error(f"[{device_id}] execute_action 失敗: action={action}, error={e}")
            return WriteResult(
                status=WriteStatus.WRITE_FAILED,
                point_name=action,
                value=params if params else None,
                error_message=str(e),
            )

    @property
    def available_actions(self) -> list[str]:
        """取得支援的動作列表"""
        return list(self.ACTIONS.keys())


__all__ = [
    "AlarmMixin",
    "WriteMixin",
]
