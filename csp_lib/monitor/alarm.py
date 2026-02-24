# =============== Monitor - Alarm ===============
#
# 系統告警評估
#
# 複用 equipment.alarm 模組的 ThresholdAlarmEvaluator 與 AlarmStateManager，
# 提供系統指標（CPU/RAM/Disk）的閾值告警：
#   - SystemAlarmEvaluator: 系統告警評估外觀

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.equipment.alarm.definition import AlarmDefinition, AlarmLevel, HysteresisConfig
from csp_lib.equipment.alarm.evaluator import Operator, ThresholdAlarmEvaluator, ThresholdCondition
from csp_lib.equipment.alarm.state import AlarmEvent, AlarmStateManager

if TYPE_CHECKING:
    from csp_lib.monitor.collector import SystemMetrics
    from csp_lib.monitor.config import MonitorConfig


def create_system_alarm_evaluators(config: MonitorConfig) -> dict[str, ThresholdAlarmEvaluator]:
    """
    建立系統告警評估器

    Args:
        config: 監控器配置

    Returns:
        {指標名稱: 閾值評估器} 字典
    """
    hysteresis = HysteresisConfig(
        activate_threshold=config.hysteresis_activate,
        clear_threshold=config.hysteresis_clear,
    )
    evaluators: dict[str, ThresholdAlarmEvaluator] = {}

    if config.enable_cpu:
        evaluators["cpu_percent"] = ThresholdAlarmEvaluator(
            point_name="cpu_percent",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition(
                        code="SYS_CPU_HIGH",
                        name="系統 CPU 使用率過高",
                        level=AlarmLevel.WARNING,
                        hysteresis=hysteresis,
                        description=f"CPU 使用率超過 {config.thresholds.cpu_percent}%",
                    ),
                    operator=Operator.GT,
                    value=config.thresholds.cpu_percent,
                ),
            ],
        )

    if config.enable_ram:
        evaluators["ram_percent"] = ThresholdAlarmEvaluator(
            point_name="ram_percent",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition(
                        code="SYS_RAM_HIGH",
                        name="系統 RAM 使用率過高",
                        level=AlarmLevel.WARNING,
                        hysteresis=hysteresis,
                        description=f"RAM 使用率超過 {config.thresholds.ram_percent}%",
                    ),
                    operator=Operator.GT,
                    value=config.thresholds.ram_percent,
                ),
            ],
        )

    if config.enable_disk:
        for path in config.disk_paths:
            safe_path = path.replace("/", "_").strip("_") or "root"
            code = f"SYS_DISK_HIGH_{safe_path}"
            evaluators[f"disk:{path}"] = ThresholdAlarmEvaluator(
                point_name=f"disk:{path}",
                conditions=[
                    ThresholdCondition(
                        alarm=AlarmDefinition(
                            code=code,
                            name=f"磁碟 {path} 使用率過高",
                            level=AlarmLevel.ALARM,
                            hysteresis=hysteresis,
                            description=f"磁碟 {path} 使用率超過 {config.thresholds.disk_percent}%",
                        ),
                        operator=Operator.GT,
                        value=config.thresholds.disk_percent,
                    ),
                ],
            )

    return evaluators


class SystemAlarmEvaluator:
    """
    系統告警評估外觀

    整合 ThresholdAlarmEvaluator 與 AlarmStateManager，
    提供單一 evaluate(metrics) 介面。
    """

    def __init__(self, config: MonitorConfig) -> None:
        self._config = config
        self._evaluators = create_system_alarm_evaluators(config)
        self._state_manager = AlarmStateManager()
        self._network_evaluators: dict[str, dict[str, ThresholdAlarmEvaluator]] = {}

        # 註冊所有告警定義
        for evaluator in self._evaluators.values():
            self._state_manager.register_alarms(evaluator.get_alarms())

    def _get_or_create_network_evaluators(self, iface_name: str) -> dict[str, ThresholdAlarmEvaluator]:
        """取得或建立網路介面告警評估器"""
        if iface_name in self._network_evaluators:
            return self._network_evaluators[iface_name]

        thresholds = self._config.network_thresholds
        hysteresis = HysteresisConfig(
            activate_threshold=self._config.hysteresis_activate,
            clear_threshold=self._config.hysteresis_clear,
        )
        safe_name = iface_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        evaluators: dict[str, ThresholdAlarmEvaluator] = {}

        if thresholds.send_rate_bytes > 0:
            code = f"SYS_NET_SEND_HIGH_{safe_name}"
            ev = ThresholdAlarmEvaluator(
                point_name=f"net_send:{iface_name}",
                conditions=[
                    ThresholdCondition(
                        alarm=AlarmDefinition(
                            code=code,
                            name=f"網路介面 {iface_name} 發送速率過高",
                            level=AlarmLevel.WARNING,
                            hysteresis=hysteresis,
                            description=f"網路介面 {iface_name} 發送速率超過 {thresholds.send_rate_bytes} bytes/s",
                        ),
                        operator=Operator.GT,
                        value=thresholds.send_rate_bytes,
                    ),
                ],
            )
            evaluators["send"] = ev
            self._state_manager.register_alarms(ev.get_alarms())

        if thresholds.recv_rate_bytes > 0:
            code = f"SYS_NET_RECV_HIGH_{safe_name}"
            ev = ThresholdAlarmEvaluator(
                point_name=f"net_recv:{iface_name}",
                conditions=[
                    ThresholdCondition(
                        alarm=AlarmDefinition(
                            code=code,
                            name=f"網路介面 {iface_name} 接收速率過高",
                            level=AlarmLevel.WARNING,
                            hysteresis=hysteresis,
                            description=f"網路介面 {iface_name} 接收速率超過 {thresholds.recv_rate_bytes} bytes/s",
                        ),
                        operator=Operator.GT,
                        value=thresholds.recv_rate_bytes,
                    ),
                ],
            )
            evaluators["recv"] = ev
            self._state_manager.register_alarms(ev.get_alarms())

        self._network_evaluators[iface_name] = evaluators
        return evaluators

    def evaluate(self, metrics: SystemMetrics) -> list[AlarmEvent]:
        """
        評估系統指標並返回告警事件

        Args:
            metrics: 系統指標

        Returns:
            告警事件列表（狀態變化時產生）
        """
        all_evaluations: dict[str, bool] = {}

        # CPU
        if "cpu_percent" in self._evaluators:
            result = self._evaluators["cpu_percent"].evaluate(metrics.cpu_percent)
            all_evaluations.update(result)

        # RAM
        if "ram_percent" in self._evaluators:
            result = self._evaluators["ram_percent"].evaluate(metrics.ram_percent)
            all_evaluations.update(result)

        # Disk
        for path, percent in metrics.disk_usage.items():
            key = f"disk:{path}"
            if key in self._evaluators:
                result = self._evaluators[key].evaluate(percent)
                all_evaluations.update(result)

        # Network interfaces
        if self._config.network_thresholds.is_enabled:
            for iface_name, iface_metrics in metrics.interface_metrics.items():
                net_evaluators = self._get_or_create_network_evaluators(iface_name)
                if "send" in net_evaluators:
                    result = net_evaluators["send"].evaluate(iface_metrics.send_rate)
                    all_evaluations.update(result)
                if "recv" in net_evaluators:
                    result = net_evaluators["recv"].evaluate(iface_metrics.recv_rate)
                    all_evaluations.update(result)

        return self._state_manager.update(all_evaluations)

    @property
    def active_alarms(self) -> list[str]:
        """取得活躍告警代碼列表"""
        return [state.definition.code for state in self._state_manager.get_active_alarms()]

    @property
    def state_manager(self) -> AlarmStateManager:
        """取得告警狀態管理器"""
        return self._state_manager


__all__ = [
    "SystemAlarmEvaluator",
    "create_system_alarm_evaluators",
]
