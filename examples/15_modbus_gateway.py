"""
Example 15: ModbusGatewayServer — Modbus TCP Gateway

Demonstrates:
  - GatewayRegisterDef: 宣告式暫存器定義（HR/IR, scale, data type）
  - WriteRule: 寫入範圍驗證 + clamp
  - AddressWhitelistValidator: 位址白名單
  - CallbackHook: 寫入觸發回呼
  - PollingCallbackSource: 定期資料同步
  - CommunicationWatchdog: 通訊逾時告警
  - SystemControllerConfig.builder() 整合

Scenario:
  模擬一台 500kW ESS，透過 Modbus TCP port 5020 對外暴露：
    HR（EMS 可讀寫）:
      addr 0-1: 功率指令 (INT32, kW)
      addr 4:   控制模式 (UINT16, 1=grid/2=pcs)
    IR（唯讀）:
      addr 100: SOC (UINT16, ×10)
      addr 101: 電池狀態 (UINT16, 0=ok/1=fault)

  EMS 寫入功率指令 → WriteRule clamp ±500kW → CallbackHook 印出
  背景 PollingCallbackSource 每秒更新 SOC/battery_status
  Watchdog 10 秒無通訊 → 告警回呼
"""

from __future__ import annotations

import asyncio

from csp_lib.core import get_logger, set_level
from csp_lib.modbus import Int32, UInt16
from csp_lib.modbus_gateway import (
    AddressWhitelistValidator,
    CallbackHook,
    GatewayRegisterDef,
    GatewayServerConfig,
    ModbusGatewayServer,
    PollingCallbackSource,
    RegisterType,
    WatchdogConfig,
    WriteRule,
)

logger = get_logger("example")
set_level("INFO")


# ─────────────────────── 寫入回呼 ───────────────────────


async def on_ems_write(register_name: str, old_value, new_value) -> None:
    """EMS 寫入時觸發"""
    logger.info(f"[WriteHook] EMS 寫入: {register_name} = {old_value} → {new_value}")


# ─────────────────────── 資料來源 ───────────────────────

_fake_soc = 75.0
_fake_status = 0


async def get_device_state() -> dict:
    """模擬從設備讀取狀態（每秒呼叫一次）"""
    global _fake_soc
    _fake_soc -= 0.1  # 模擬放電 SOC 下降
    return {
        "soc": round(_fake_soc, 1),
        "battery_status": _fake_status,
    }


# ─────────────────────── Watchdog 回呼 ───────────────────────


async def on_comm_timeout() -> None:
    logger.warning("[Watchdog] 通訊逾時！EMS 已超過 10 秒無通訊")


async def on_comm_recover() -> None:
    logger.info("[Watchdog] 通訊恢復")


# ─────────────────────── Main ───────────────────────


async def main():
    logger.info("=" * 50)
    logger.info("  ModbusGatewayServer Example")
    logger.info("=" * 50)

    # ── 暫存器定義 ──
    registers = [
        # Holding Registers（EMS 可讀寫）
        GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, description="功率指令 (kW)"),
        GatewayRegisterDef("mode_select", 4, UInt16(), RegisterType.HOLDING, initial_value=1, description="控制模式"),
        # Input Registers（唯讀，由系統更新）
        GatewayRegisterDef("soc", 100, UInt16(), RegisterType.INPUT, scale=10, description="SOC (×0.1%)"),
        GatewayRegisterDef("battery_status", 101, UInt16(), RegisterType.INPUT, description="電池狀態"),
    ]

    # ── 寫入規則 ──
    write_rules = {
        "p_command": WriteRule(register_name="p_command", min_value=-500, max_value=500, clamp=True),
    }

    # ── 伺服器配置 ──
    config = GatewayServerConfig(
        host="0.0.0.0",
        port=5020,  # 非特權埠，避免需要 root
        unit_id=1,
        watchdog=WatchdogConfig(timeout_seconds=10, check_interval=2),
    )

    # ── 建立 Gateway ──
    async with ModbusGatewayServer(
        config,
        registers,
        write_rules=write_rules,
        validators=[AddressWhitelistValidator({"p_command", "mode_select"})],
        hooks=[CallbackHook(on_ems_write)],
        sync_sources=[PollingCallbackSource(get_device_state, interval=1.0)],
    ) as gw:
        # 註冊 watchdog 回呼
        gw.watchdog.on_timeout(on_comm_timeout)
        gw.watchdog.on_recover(on_comm_recover)

        logger.info(f"Gateway 啟動於 port {config.port}")
        logger.info("暫存器佈局:")
        logger.info("  HR[0-1]  p_command     INT32  ±500kW (clamp)")
        logger.info("  HR[4]    mode_select   UINT16 1=grid/2=pcs")
        logger.info("  IR[100]  soc           UINT16 ×0.1%")
        logger.info("  IR[101]  battery_status UINT16")
        logger.info("")
        logger.info("測試方式（另開終端）:")
        logger.info("  # 讀 SOC:")
        logger.info("  pymodbus.console tcp --host localhost --port 5020 --unit 1")
        logger.info("  > client.read_input_registers address=100 count=1")
        logger.info("")
        logger.info("  # 寫功率指令:")
        logger.info("  > client.write_registers address=0 values=[0,300]")
        logger.info("")
        logger.info("按 Ctrl+C 停止")

        # 每 3 秒印出當前暫存器值
        try:
            while True:
                await asyncio.sleep(3)
                vals = gw.get_all_registers()
                logger.info(
                    f"[State] p_cmd={vals.get('p_command', 0)}kW  "
                    f"mode={vals.get('mode_select', 1)}  "
                    f"SOC={vals.get('soc', 0):.1f}%  "
                    f"bat={vals.get('battery_status', 0)}"
                )
        except asyncio.CancelledError:
            pass

    logger.info("Gateway 已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
