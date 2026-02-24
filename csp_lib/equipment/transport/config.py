# =============== Equipment Transport - Config ===============
#
# 傳輸層配置
#
# 定義點位分組器的配置：
#   - PointGrouperConfig: 各功能碼的最大讀取長度

from __future__ import annotations

from dataclasses import dataclass, field


def _default_fc_max_length() -> dict[int, int]:
    return {
        1: 2000,  # Read Coils
        2: 2000,  # Read Discrete Inputs
        3: 125,  # Read Holding Registers
        4: 125,  # Read Input Registers
    }


@dataclass(frozen=True)
class PointGrouperConfig:
    """
    點位分組器配置

    Attributes:
        fc_max_length: 各功能碼的最大讀取長度
    """

    fc_max_length: dict[int, int] = field(default_factory=_default_fc_max_length)

    def __post_init__(self) -> None:
        for fc, length in self.fc_max_length.items():
            if length <= 0:
                raise ValueError(f"功能碼 {fc} 的最大讀取長度必須大於 0，收到: {length}")


__all__ = [
    "PointGrouperConfig",
]
