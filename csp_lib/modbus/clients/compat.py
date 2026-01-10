# =============== Pymodbus Version Compatibility ===============
#
# pymodbus 版本相容性層
#
# 處理 pymodbus 3.10.0+ API 變更：
#   - slave/slaves → device_id/device_ids

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _get_pymodbus_version() -> tuple[int, int, int]:
    """
    取得 pymodbus 版本號

    Returns:
        (major, minor, patch) 版本元組
    """
    try:
        import pymodbus

        version_str = pymodbus.__version__
        parts = version_str.split(".")
        return (
            int(parts[0]) if len(parts) > 0 else 0,
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2].split("-")[0]) if len(parts) > 2 else 0,  # 處理 "3.10.0-dev"
        )
    except (ImportError, ValueError, AttributeError):
        # 預設使用新版 API
        return (3, 10, 0)


def is_new_api() -> bool:
    """
    檢查是否使用新版 API (>= 3.10.0)

    pymodbus 3.10.0 後：
    - slave → device_id
    - slaves → device_ids
    """
    major, minor, _ = _get_pymodbus_version()
    return (major, minor) >= (3, 10)


def slave_kwarg(unit_id: int) -> dict[str, int]:
    """
    根據 pymodbus 版本返回正確的 slave/device_id 參數

    這是內部 API，用於 pymodbus_client.py 中的客戶端實作。
    一般使用者不需要直接呼叫此函數。

    Args:
        unit_id: 設備位址

    Returns:
        {"device_id": unit_id} (pymodbus >= 3.10.0)
        或 {"slave": unit_id} (pymodbus < 3.10.0)
    """
    if is_new_api():
        return {"device_id": unit_id}
    return {"slave": unit_id}


__all__ = [
    "is_new_api",
    "slave_kwarg",
]
