# =============== Core - Logging - File Config ===============
#
# 檔案 Sink 配置
#
# 提供檔案 sink 的不可變配置物件：
#   - FileSinkConfig: loguru file sink 的完整配置

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileSinkConfig:
    """檔案 Sink 配置。

    封裝 loguru file sink 所需的全部參數，使用不可變 dataclass。

    Attributes:
        path: 檔案路徑。
        rotation: 輪替條件（如 ``"100 MB"``、``"1 day"``）。
        retention: 保留策略（如 ``"30 days"``、``10``）。
        compression: 壓縮格式（如 ``"zip"``、``"gz"``）。
        level: 最低 log 等級。
        format: 自訂格式字串。
        enqueue: 是否使用佇列寫入（多執行緒安全）。
        serialize: 是否以 JSON 格式輸出。
        encoding: 檔案編碼。
        name: Sink 名稱（用於 SinkManager 查詢）。

    Example:
        ```python
        config = FileSinkConfig(
            path="/var/log/csp/app.log",
            rotation="100 MB",
            retention="30 days",
            compression="zip",
        )
        ```
    """

    path: str
    rotation: str | int | None = "100 MB"
    retention: str | int | None = "30 days"
    compression: str | None = None
    level: str = "DEBUG"
    format: str | None = None
    enqueue: bool = True
    serialize: bool = False
    encoding: str = "utf-8"
    name: str | None = None


__all__ = [
    "FileSinkConfig",
]
