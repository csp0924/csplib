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
    except (ImportError, ValueError, AttributeError, IndexError):
        # 預設使用新版 API
        return (3, 10, 0)


def _is_new_api() -> bool:
    """
    檢查是否使用新版 API (>= 3.10.0)

    pymodbus 3.10.0 後：
    - slave → device_id
    - slaves → device_ids

    Internal helper，僅供 csp_lib.modbus.clients 內部使用。
    """
    major, minor, _ = _get_pymodbus_version()
    return (major, minor) >= (3, 10)


def _slave_kwarg(unit_id: int) -> dict[str, int]:
    """
    根據 pymodbus 版本返回正確的 slave/device_id 參數

    Internal helper，僅供 csp_lib.modbus.clients 內部使用，
    請勿在 modbus 模組外直接引用。

    Args:
        unit_id: 設備位址

    Returns:
        {"device_id": unit_id} (pymodbus >= 3.10.0)
        或 {"slave": unit_id} (pymodbus < 3.10.0)
    """
    if _is_new_api():
        return {"device_id": unit_id}
    return {"slave": unit_id}


# ---- Backward-compatible deprecated aliases (v0.10.0 將移除) ----
# 原本 `is_new_api` / `slave_kwarg` 公開於 csp_lib.modbus.clients；本次 rename
# 為 `_` prefix 標示 internal，但保留公開別名一版供下游過渡期使用。


def is_new_api() -> bool:  # noqa: D401 — deprecated alias
    """Deprecated alias of :func:`_is_new_api`. Will be removed in v0.10.0."""
    import warnings

    warnings.warn(
        "csp_lib.modbus.clients.is_new_api 已更名為內部函式 _is_new_api，"
        "將於 v0.10.0 移除；此 helper 僅供 modbus 模組內部使用。",
        DeprecationWarning,
        stacklevel=2,
    )
    return _is_new_api()


def slave_kwarg(unit_id: int) -> dict[str, int]:  # noqa: D401
    """Deprecated alias of :func:`_slave_kwarg`. Will be removed in v0.10.0."""
    import warnings

    warnings.warn(
        "csp_lib.modbus.clients.slave_kwarg 已更名為內部函式 _slave_kwarg，"
        "將於 v0.10.0 移除；此 helper 僅供 modbus 模組內部使用。",
        DeprecationWarning,
        stacklevel=2,
    )
    return _slave_kwarg(unit_id)


__all__: list[str] = ["is_new_api", "slave_kwarg"]
