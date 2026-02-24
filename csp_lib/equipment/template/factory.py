# =============== Equipment Template - Factory ===============
#
# 設備工廠
#
# 從範本建立 AsyncModbusDevice 實例：
#   - DeviceFactory.create: 建立單一設備
#   - DeviceFactory.create_batch: 批次建立（各自 config）
#   - DeviceFactory.create_stride: 固定步幅批次建立

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Callable, Sequence

from csp_lib.equipment.device.base import AsyncModbusDevice

from .definition import EquipmentTemplate, PointOverride

if TYPE_CHECKING:
    from csp_lib.equipment.alarm import AlarmEvaluator
    from csp_lib.equipment.core import ReadPoint, WritePoint
    from csp_lib.equipment.device.config import DeviceConfig
    from csp_lib.modbus.clients.base import AsyncModbusClientBase


def _apply_offset_to_read_points(points: tuple[ReadPoint, ...], offset: int) -> tuple[ReadPoint, ...]:
    """對讀取點位套用位址偏移"""
    if offset == 0:
        return points
    return tuple(replace(p, address=p.address + offset) for p in points)


def _apply_offset_to_write_points(points: tuple[WritePoint, ...], offset: int) -> tuple[WritePoint, ...]:
    """對寫入點位套用位址偏移"""
    if offset == 0:
        return points
    return tuple(replace(p, address=p.address + offset) for p in points)


def _apply_overrides_to_read_points(
    points: tuple[ReadPoint, ...],
    overrides: dict[str, PointOverride],
) -> tuple[ReadPoint, ...]:
    """對讀取點位套用覆寫（重新命名、更新元資料）"""
    result: list[ReadPoint] = []
    for p in points:
        override = overrides.get(p.name)
        if override is not None:
            kwargs: dict = {"name": override.name}
            if override.metadata is not None:
                kwargs["metadata"] = override.metadata
            result.append(replace(p, **kwargs))
        else:
            result.append(p)
    return tuple(result)


def _apply_overrides_to_write_points(
    points: tuple[WritePoint, ...],
    overrides: dict[str, PointOverride],
) -> tuple[WritePoint, ...]:
    """對寫入點位套用覆寫（重新命名）"""
    result: list[WritePoint] = []
    for p in points:
        override = overrides.get(p.name)
        if override is not None:
            result.append(replace(p, name=override.name))
        else:
            result.append(p)
    return tuple(result)


def _build_name_map(overrides: dict[str, PointOverride]) -> dict[str, str]:
    """建立原始名稱 -> 新名稱的映射"""
    return {old_name: ov.name for old_name, ov in overrides.items()}


def _apply_overrides_to_evaluators(
    evaluators: tuple[AlarmEvaluator, ...],
    name_map: dict[str, str],
) -> tuple[AlarmEvaluator, ...]:
    """更新告警評估器的 point_name 參照"""
    if not name_map:
        return evaluators
    return tuple(
        replace(e, point_name=name_map[e.point_name]) if e.point_name in name_map else e  # type: ignore[type-var]
        for e in evaluators
    )


class DeviceFactory:
    """
    設備工廠

    從 EquipmentTemplate 建立 AsyncModbusDevice 實例。
    """

    @staticmethod
    def create(
        template: EquipmentTemplate,
        config: DeviceConfig,
        client: AsyncModbusClientBase,
        *,
        overrides: dict[str, PointOverride] | None = None,
        address_offset: int = 0,
    ) -> AsyncModbusDevice:
        """
        從範本建立單一設備

        Args:
            template: 設備範本
            config: 設備設定（device_id, unit_id 等）
            client: Modbus 客戶端
            overrides: 點位覆寫（按原始名稱索引）
            address_offset: 位址偏移（加到每個點位的 address）

        Returns:
            設定好的 AsyncModbusDevice 實例
        """
        always_points = template.always_points
        rotating_points = template.rotating_points
        write_points = template.write_points
        alarm_evaluators = template.alarm_evaluators

        # 套用覆寫
        if overrides:
            name_map = _build_name_map(overrides)
            always_points = _apply_overrides_to_read_points(always_points, overrides)
            rotating_points = tuple(
                _apply_overrides_to_read_points(group, overrides) for group in rotating_points
            )
            write_points = _apply_overrides_to_write_points(write_points, overrides)
            alarm_evaluators = _apply_overrides_to_evaluators(alarm_evaluators, name_map)

        # 套用位址偏移
        if address_offset != 0:
            always_points = _apply_offset_to_read_points(always_points, address_offset)
            rotating_points = tuple(
                _apply_offset_to_read_points(group, address_offset) for group in rotating_points
            )
            write_points = _apply_offset_to_write_points(write_points, address_offset)

        return AsyncModbusDevice(
            config=config,
            client=client,
            always_points=always_points,
            rotating_points=rotating_points,
            write_points=write_points,
            alarm_evaluators=alarm_evaluators,
            aggregator_pipeline=template.aggregator_pipeline,
            capability_bindings=template.capability_bindings,
        )

    @staticmethod
    def create_batch(
        template: EquipmentTemplate,
        instances: Sequence[DeviceConfig],
        client_factory: Callable[[DeviceConfig], AsyncModbusClientBase],
        *,
        overrides: dict[str, PointOverride] | None = None,
        address_offsets: Sequence[int] | None = None,
    ) -> list[AsyncModbusDevice]:
        """
        批次建立設備

        Args:
            template: 設備範本
            instances: 各設備設定
            client_factory: 根據設定建立/取得客戶端的工廠函式
            overrides: 點位覆寫（所有實例共用）
            address_offsets: 各實例的位址偏移（長度需與 instances 一致）

        Returns:
            AsyncModbusDevice 實例列表

        Raises:
            ValueError: address_offsets 長度與 instances 不一致
        """
        if address_offsets is not None and len(address_offsets) != len(instances):
            raise ValueError(
                f"address_offsets 長度 ({len(address_offsets)}) 與 instances 長度 ({len(instances)}) 不一致"
            )

        devices: list[AsyncModbusDevice] = []
        for i, config in enumerate(instances):
            offset = address_offsets[i] if address_offsets is not None else 0
            client = client_factory(config)
            device = DeviceFactory.create(
                template=template,
                config=config,
                client=client,
                overrides=overrides,
                address_offset=offset,
            )
            devices.append(device)

        return devices

    @staticmethod
    def create_stride(
        template: EquipmentTemplate,
        base_config: DeviceConfig,
        client_factory: Callable[[DeviceConfig], AsyncModbusClientBase],
        count: int,
        stride: int,
        *,
        id_format: str = "{base_id}_{index}",
        overrides: dict[str, PointOverride] | None = None,
    ) -> list[AsyncModbusDevice]:
        """
        固定步幅批次建立設備

        適用於相同點位但位址偏移固定的場景（如 sub_bms1~10）。

        Args:
            template: 設備範本
            base_config: 基礎設定（device_id 作為格式化來源）
            client_factory: 根據設定建立/取得客戶端的工廠函式
            count: 設備數量
            stride: 位址步幅
            id_format: device_id 格式字串（支援 {base_id} 和 {index}）
            overrides: 點位覆寫（所有實例共用）

        Returns:
            AsyncModbusDevice 實例列表
        """
        instances = [
            replace(base_config, device_id=id_format.format(base_id=base_config.device_id, index=i + 1))
            for i in range(count)
        ]
        offsets = [i * stride for i in range(count)]

        return DeviceFactory.create_batch(
            template=template,
            instances=instances,
            client_factory=client_factory,
            overrides=overrides,
            address_offsets=offsets,
        )


__all__ = [
    "DeviceFactory",
]
