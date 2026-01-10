# =============== Modbus Exceptions ===============
#
# Modbus 模組例外類型定義
#
# 例外繼承結構：
#   ModbusError (基礎)
#   ├── ModbusEncodeError (編碼錯誤)
#   ├── ModbusDecodeError (解碼錯誤)
#   └── ModbusConfigError (設定錯誤)

from __future__ import annotations


class ModbusError(Exception):
    """
    Modbus 基礎例外

    所有 Modbus 相關例外的父類別，方便統一捕捉。
    """


class ModbusEncodeError(ModbusError):
    """
    編碼錯誤

    當編碼過程失敗時拋出，常見原因：
    - 值超出資料類型允許範圍 (e.g., int16 超過 32767)
    - 類型不符 (e.g., 傳入字串給數值類型)
    """


class ModbusDecodeError(ModbusError):
    """
    解碼錯誤

    當解碼過程失敗時拋出，常見原因：
    - 暫存器資料長度不足
    - 資料格式錯誤 (e.g., 無效的 IEEE 754 格式)
    """


class ModbusConfigError(ModbusError):
    """
    設定錯誤

    當設定參數無效時拋出，常見原因：
    - 無效的連線參數 (e.g., 負的 port 號)
    - 無效的資料類型參數 (e.g., bit_width 非 16 的倍數)
    """


__all__ = [
    "ModbusError",
    "ModbusEncodeError",
    "ModbusDecodeError",
    "ModbusConfigError",
]
