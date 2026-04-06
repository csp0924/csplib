"""
Example 14: Logging System — v0.7.0 日誌系統

學習目標:
  - configure_logging(): 基本日誌配置
  - set_level(): 模組等級控制
  - LogFilter: 自訂過濾器（最長前綴匹配）
  - SinkManager: 管理多個 sink（stderr + file）
  - LogContext: 結構化日誌上下文（correlation ID）
  - LogCapture: 測試輔助（攔截日誌輸出）
  - FileSinkConfig: 檔案 sink 配置

架構:
  loguru logger
    └─ SinkManager (全域單例)
         ├─ stderr sink (LogFilter 過濾)
         ├─ file sink (FileSinkConfig)
         └─ LogCapture (測試用)
    └─ LogFilter
         ├─ default_level: INFO
         └─ module_levels: {"csp_lib.modbus": "DEBUG", ...}
    └─ LogContext (ContextVar)
         └─ 巢狀 bindings (request_id, device_id, ...)

Run: uv run python examples/13_logging_system.py
預計時間: 15 min
"""

import asyncio
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.core import (
    DEFAULT_FORMAT,
    FileSinkConfig,
    LogCapture,
    LogContext,
    LogFilter,
    SinkManager,
    add_file_sink,
    configure_logging,
    get_logger,
    set_level,
)

# ============================================================
# Step 1: 基本 Logging 配置
# ============================================================


def demo_basic_logging() -> None:
    """展示 configure_logging() 和 get_logger()"""
    print("\n=== Step 1: 基本 Logging 配置 ===")

    # 初始化日誌系統（移除預設 sink，新增 stderr sink）
    configure_logging(level="INFO")
    print("  configure_logging(level='INFO') 完成")

    # 取得模組 logger
    logger = get_logger("example.logging")
    logger.info("基本日誌訊息")
    logger.debug("這條 DEBUG 不會顯示 (預設 INFO)")

    # 驗證 SinkManager 狀態
    mgr = SinkManager.get_instance()
    sinks = mgr.list_sinks()
    print(f"\n  Sink 數量: {len(sinks)}")
    for sink in sinks:
        print(f"    [{sink.sink_type}] id={sink.sink_id} name='{sink.name}' level={sink.level}")

    print(f"  預設格式: {DEFAULT_FORMAT[:50]}...")


# ============================================================
# Step 2: 模組等級控制
# ============================================================


def demo_module_level() -> None:
    """展示 set_level() 的模組等級控制"""
    print("\n=== Step 2: 模組等級控制 ===")

    configure_logging(level="INFO")

    # 為特定模組設定 DEBUG
    set_level("DEBUG", module="csp_lib.modbus")
    print("  set_level('DEBUG', module='csp_lib.modbus')")

    # 不同模組的 logger
    modbus_logger = get_logger("csp_lib.modbus")
    equipment_logger = get_logger("csp_lib.equipment")

    modbus_logger.debug("Modbus DEBUG 可見 (已設 DEBUG)")
    equipment_logger.debug("Equipment DEBUG 不可見 (預設 INFO)")
    equipment_logger.info("Equipment INFO 可見")

    # 查看各模組有效等級
    mgr = SinkManager.get_instance()
    log_filter = mgr.filter
    print(f"\n  csp_lib.modbus 有效等級: {log_filter.get_effective_level('csp_lib.modbus')}")
    print(f"  csp_lib.equipment 有效等級: {log_filter.get_effective_level('csp_lib.equipment')}")
    print(f"  csp_lib.modbus.tcp 有效等級: {log_filter.get_effective_level('csp_lib.modbus.tcp')} (前綴匹配)")


# ============================================================
# Step 3: LogFilter 自訂過濾
# ============================================================


def demo_log_filter() -> None:
    """展示 LogFilter 的最長前綴匹配邏輯"""
    print("\n=== Step 3: LogFilter 自訂過濾 ===")

    f = LogFilter(default_level="WARNING")
    print(f"  預設等級: {f.default_level}")

    # 設定多層模組等級
    f.set_module_level("csp_lib", "INFO")
    f.set_module_level("csp_lib.modbus", "DEBUG")
    f.set_module_level("csp_lib.modbus.tcp", "TRACE")

    # 展示最長前綴匹配
    test_modules = [
        "other_lib",  # → WARNING (預設)
        "csp_lib",  # → INFO
        "csp_lib.core",  # → INFO (匹配 csp_lib)
        "csp_lib.modbus",  # → DEBUG (精確匹配)
        "csp_lib.modbus.tcp",  # → TRACE (精確匹配)
        "csp_lib.modbus.rtu",  # → DEBUG (匹配 csp_lib.modbus)
    ]
    for mod in test_modules:
        level = f.get_effective_level(mod)
        print(f"  {mod:30s} → {level}")

    # 移除特定模組設定
    f.remove_module_level("csp_lib.modbus.tcp")
    level = f.get_effective_level("csp_lib.modbus.tcp")
    print(f"\n  移除 tcp 設定後: csp_lib.modbus.tcp → {level} (回到 csp_lib.modbus)")

    # 查看所有模組設定
    print(f"  模組設定: {f.module_levels}")


# ============================================================
# Step 4: SinkManager 管理多個 sink
# ============================================================


def demo_sink_manager() -> None:
    """展示 SinkManager 管理多個 sink"""
    print("\n=== Step 4: SinkManager 管理多個 sink ===")

    configure_logging(level="INFO")
    mgr = SinkManager.get_instance()

    # 新增檔案 sink
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "example.log"

        file_config = FileSinkConfig(
            path=str(log_path),
            rotation="10 MB",
            retention="7 days",
            compression=None,
            level="DEBUG",
            enqueue=True,
            name="example_file",
        )
        file_sink_id = add_file_sink(file_config)
        print(f"  新增檔案 sink: id={file_sink_id}, path={log_path}")

        # 列出所有 sinks
        sinks = mgr.list_sinks()
        print(f"\n  目前 sink 數量: {len(sinks)}")
        for sink in sinks:
            print(f"    [{sink.sink_type:6s}] id={sink.sink_id} name='{sink.name}' level={sink.level}")

        # 按名稱查詢
        info = mgr.get_sink("example_file")
        print(f"\n  查詢 'example_file': {info}")

        # 寫入一些日誌
        logger = get_logger("example.sink")
        logger.info("這條會寫入 stderr 和 file")
        logger.debug("這條只寫入 file (stderr 是 INFO)")

        # 檢查檔案是否有內容
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            print(f"\n  檔案內容行數: {len(lines)}")
            for line in lines[:3]:
                print(f"    {line[:80]}...")

        # 移除檔案 sink
        mgr.remove_sink(file_sink_id)
        print(f"\n  已移除 sink id={file_sink_id}")
        print(f"  目前 sink 數量: {len(mgr.list_sinks())}")


# ============================================================
# Step 5: LogContext 結構化日誌
# ============================================================


async def demo_log_context() -> None:
    """展示 LogContext 結構化日誌上下文"""
    print("\n=== Step 5: LogContext 結構化日誌上下文 ===")

    configure_logging(
        level="DEBUG",
        # 加入 extra 欄位顯示 context bindings
        format_string=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]}</cyan> | "
            "{message} | "
            "ctx={extra}"
        ),
    )

    logger = get_logger("example.context")

    # 同步 context manager
    print("  --- 同步 context ---")
    with LogContext(request_id="REQ-001", user="admin"):
        logger.info("處理請求")

        # 巢狀 context（繼承外層 + 覆蓋）
        with LogContext(step="validation"):
            logger.info("驗證參數")

    # 離開 context 後 bindings 消失
    logger.info("context 外部 (無 bindings)")

    # 非同步 context manager
    print("\n  --- 非同步 context ---")
    async with LogContext(device_id="PCS-01", operation="calibrate"):
        logger.info("開始校準")
        await asyncio.sleep(0.1)
        logger.info("校準完成")

    # Decorator 用法
    print("\n  --- Decorator 用法 ---")

    @LogContext(task="scheduled_check")
    async def check_status() -> None:
        logger.info("執行排程檢查")

    await check_status()

    # 直接 bind/unbind
    print("\n  --- 直接 bind/unbind ---")
    LogContext.bind(session="S-123")
    logger.info("有 session binding")
    LogContext.unbind("session")
    logger.info("已移除 session binding")

    # 查看當前 context
    with LogContext(a=1, b=2):
        current = LogContext.current()
        print(f"\n  當前 context: {current}")

    # 恢復預設格式
    configure_logging(level="INFO")


# ============================================================
# Step 6: LogCapture 測試輔助
# ============================================================


def demo_log_capture() -> None:
    """展示 LogCapture 測試輔助工具"""
    print("\n=== Step 6: LogCapture 測試輔助 ===")

    logger = get_logger("example.capture")

    # 在 context manager 內攔截所有日誌
    with LogCapture(level="DEBUG") as cap:
        logger.info("第一條訊息")
        logger.debug("除錯訊息")
        logger.warning("警告訊息")
        logger.info("包含關鍵字 device_error 的訊息")

    # 查詢結果
    print(f"  捕獲記錄數: {len(cap.records)}")
    for rec in cap.records:
        print(f"    [{rec.level:8s}] {rec.module}: {rec.message}")

    # contains() — 檢查是否存在
    print(f"\n  contains('第一條'): {cap.contains('第一條')}")
    print(f"  contains('第一條', level='INFO'): {cap.contains('第一條', level='INFO')}")
    print(f"  contains('不存在'): {cap.contains('不存在')}")

    # filter() — 條件過濾
    warnings = cap.filter(level="WARNING")
    print(f"\n  WARNING 記錄數: {len(warnings)}")

    # 用正則匹配
    errors = cap.filter(message_pattern=r"device_error")
    print(f"  含 'device_error' 記錄數: {len(errors)}")

    # text — 合併所有訊息
    print(f"\n  合併文字:\n    {cap.text[:100]}...")

    # clear() — 清除
    cap.clear()
    print(f"  clear() 後記錄數: {len(cap.records)}")


# ============================================================
# Step 7: 整合演示
# ============================================================


async def demo_integration() -> None:
    """整合展示: 不同模組的日誌輸出"""
    print("\n=== Step 7: 整合演示 — 多模組日誌 ===")

    configure_logging(level="INFO")

    # 設定不同模組的等級
    set_level("DEBUG", module="csp_lib.modbus_server")
    set_level("WARNING", module="csp_lib.integration")

    # 使用 LogCapture 攔截所有日誌
    with LogCapture(level="TRACE") as cap:
        # 模擬不同模組的日誌
        server_logger = get_logger("csp_lib.modbus_server")
        integration_logger = get_logger("csp_lib.integration")
        core_logger = get_logger("csp_lib.core")

        server_logger.debug("SimulationServer tick")
        server_logger.info("Server started on 127.0.0.1:5020")
        integration_logger.info("Integration 這條不會通過 (WARNING 等級)")
        integration_logger.warning("Device offline detected")
        core_logger.info("Lifecycle: component started")

    print("  捕獲結果:")
    for rec in cap.records:
        print(f"    [{rec.level:8s}] {rec.module}: {rec.message}")

    print("\n  模組等級設定:")
    mgr = SinkManager.get_instance()
    log_filter = mgr.filter
    print(f"    預設: {log_filter.default_level}")
    for mod, level in sorted(log_filter.module_levels.items()):
        print(f"    {mod}: {level}")


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 60)
    print("  Example 14: Logging System — v0.7.0 日誌系統")
    print("=" * 60)

    demo_basic_logging()
    demo_module_level()
    demo_log_filter()
    demo_sink_manager()
    await demo_log_context()
    demo_log_capture()
    await demo_integration()

    print("\n--- 完成 ---")
    print("\n要點回顧:")
    print("  1. configure_logging() 初始化日誌（移除預設 + 新增 stderr sink）")
    print("  2. set_level() 按模組設定等級（最長前綴匹配）")
    print("  3. LogFilter 可獨立使用，實作 __call__ 作為 loguru filter")
    print("  4. SinkManager 管理多個 sink（stderr/file/async）")
    print("  5. LogContext 提供巢狀結構化上下文（ContextVar 實作）")
    print("  6. LogCapture 攔截日誌用於測試（contains/filter/text）")
    print("  7. FileSinkConfig 設定檔案 sink（rotation/retention/compression）")


if __name__ == "__main__":
    asyncio.run(main())
