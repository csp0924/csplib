# =============== Equipment Simulation Module ===============
#
# 虛擬設備模擬模組
#
# 提供用於測試的虛擬設備模擬：
#   - curve: 測試曲線定義與註冊
#   - virtual_meter: 虛擬電表模擬器

from .curve import (
    DEFAULT_REGISTRY,
    CurvePoint,
    CurveProvider,
    CurveRegistry,
    CurveType,
    curve_fp_step,
    curve_qv_step,
)
from .virtual_meter import MeterMode, MeterReading, VirtualMeter

__all__ = [
    # Curve
    "CurveType",
    "CurvePoint",
    "CurveProvider",
    "CurveRegistry",
    "DEFAULT_REGISTRY",
    "curve_fp_step",
    "curve_qv_step",
    # Virtual Meter
    "MeterMode",
    "MeterReading",
    "VirtualMeter",
]
