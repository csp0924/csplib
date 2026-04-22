# =============== Manager Device - Manager ===============
#
# 設備讀取管理器
#
# 統一管理獨立設備與群組設備的生命週期：
#   - DeviceManager: 設備管理器類別
#
# 支援模式：
#   - 獨立模式：每個設備自己跑 read_loop（適用獨立 TCP）
#   - 群組模式：Manager 順序呼叫 read_once（適用 RTU/Shared TCP）

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, Sequence, cast

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core.errors import DeviceConnectionError

from .group import DeviceGroup

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.equipment.device.protocol import DeviceProtocol

logger = get_logger(__name__)


async def _safe_device_step(
    coro: Awaitable[None],
    *,
    device_id: str,
    action: str,
    expected_exc: type[Exception] | tuple[type[Exception], ...] = DeviceConnectionError,
) -> None:
    """執行 device lifecycle 步驟並分類處理例外。

    - ``CancelledError`` 向上傳播（不吞掉 cooperative cancellation 語意）
    - ``expected_exc`` 類別（預設 ``DeviceConnectionError``）→ warn log，不附 stack
      （代表預期可能失敗，通常由背景重試處理）
    - 其他 ``Exception`` → ``logger.opt(exception=True).warning``（附 stack）

    傳 ``expected_exc=()`` 可停用「預期例外」分支，所有 Exception 都走 unexpected
    path（帶 stack trace）。_(bug-lesson: partial-failure-gather)_
    """
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except expected_exc as e:
        logger.warning("設備 {} {} 失敗: {}", device_id, action, e)
    except Exception:
        logger.opt(exception=True).warning("設備 {} {} 出現非預期例外", device_id, action)


async def _gather_per_device_with_cancel(
    devices: Sequence["DeviceProtocol"],
    coro_factory: Callable[["DeviceProtocol"], Awaitable[None]],
    *,
    failure_msg: str,
) -> None:
    """對多個 device 平行執行 coroutine，保留 CancelledError 傳播語意。

    - ``devices`` 空時直接返回
    - ``CancelledError`` 任一出現即 re-raise，中止整批（cooperative cancellation）
    - 其他 ``BaseException`` 以 ``failure_msg.format(device_id, exc)`` warn log
      （注意 loguru 用 ``{}`` 風格，這裡用 ``%`` 風格 fallback 不合適；
      故 ``failure_msg`` 必須是 loguru 格式字串）

    Args:
        devices: 設備序列
        coro_factory: ``device -> Awaitable`` 的工廠函式
        failure_msg: loguru 格式字串，須含兩個 ``{}`` 佔位：device_id 與 exception
    """
    if not devices:
        return
    results = await asyncio.gather(
        *(coro_factory(d) for d in devices),
        return_exceptions=True,
    )
    for dev, result in zip(devices, results, strict=True):
        if isinstance(result, BaseException) and not isinstance(result, Exception):
            # CancelledError / SystemExit / KeyboardInterrupt 必須傳播
            raise result
        if isinstance(result, Exception):
            # 附 stack trace 便於診斷非預期失敗
            logger.opt(exception=result).warning(failure_msg, dev.device_id, result)


def _require_lifecycle_methods(device: "DeviceProtocol", *, for_group: bool) -> None:
    """Fail-fast 驗證 device 具備 DeviceManager 執行期所需的 lifecycle 能力。

    ``DeviceProtocol`` 目前尚未納入 ``connect/disconnect/start/stop/read_once/
    ensure_event_loop_started/ensure_event_loop_stopped``（追蹤 B-P2），因此
    ``register/register_group`` 在接受 ``DeviceProtocol`` 型別的同時必須在 runtime
    確認能力齊全；否則會延後到 ``_on_start`` / ``unregister`` 才炸 ``AttributeError``
    （symptom 離 root cause 較遠，也容易被上層 ``except Exception`` 吞掉）。

    Args:
        device: 欲註冊的設備
        for_group: True 代表為群組註冊（額外要求 ``read_once`` 與事件 loop helper）

    Raises:
        ValueError: 缺少任一必要 lifecycle 方法
    """
    required_methods = ["connect", "disconnect"]
    if for_group:
        # group 模式：Manager 需呼叫 read_once，並以 public helper 控制 event loop
        # （取代舊的 device._emitter.start/stop 私有存取）
        required_methods.extend(["read_once", "ensure_event_loop_started", "ensure_event_loop_stopped"])
    else:
        required_methods.extend(["start", "stop"])

    missing = [name for name in required_methods if not callable(getattr(device, name, None))]

    if missing:
        device_id = getattr(device, "device_id", "<unknown>")
        raise ValueError(
            f"Device '{device_id}' 缺少 DeviceManager 所需 lifecycle "
            f"{'(group)' if for_group else '(standalone)'}: {', '.join(missing)}"
        )


class DeviceManager(AsyncLifecycleMixin):
    """
    設備讀取管理器

    統一管理獨立設備與群組設備的生命週期，提供一致的 start/stop 介面。

    支援兩種模式：
        1. 獨立模式 (register): 設備自己跑 read_loop，適用獨立 TCP 連線
        2. 群組模式 (register_group): Manager 順序呼叫 read_once，適用 RTU/Shared TCP

    Attributes:
        standalone_count: 獨立設備數量
        group_count: 設備群組數量

    使用範例：
        manager = DeviceManager()

        # 獨立 TCP 設備
        manager.register(tcp_device_1)
        manager.register(tcp_device_2)

        # RTU 群組（共用 Client）
        manager.register_group([rtu_1, rtu_2], interval=1.0)
        manager.register_group([rtu_3, rtu_4, rtu_5], interval=2.0)

        # 使用 context manager
        async with manager:
            await asyncio.sleep(60)  # 運行 60 秒

        # 或手動管理
        await manager.start()
        try:
            await asyncio.sleep(60)
        finally:
            await manager.stop()
    """

    def __init__(self) -> None:
        """初始化設備管理器"""
        # 型別使用 DeviceProtocol 以接受任何實作該介面的設備（AsyncModbusDevice / AsyncCANDevice 等）。
        # 內部 start/stop 仍呼叫 connect/disconnect/read_loop 等 AsyncModbusDevice 具體方法，
        # 藉由 cast 壓 mypy；未來 DeviceProtocol 補齊 lifecycle 後即可移除 cast（追蹤 B-P2）。
        self._standalone: list[DeviceProtocol] = []
        self._groups: list[DeviceGroup] = []
        self._registered_ids: set[str] = set()
        self._running = False

    # ================ 註冊 ================

    def register(self, device: DeviceProtocol) -> None:
        """
        註冊獨立設備

        獨立設備將使用自己的 read_loop 進行讀取。

        Args:
            device: 要註冊的設備（任何實作 DeviceProtocol 的裝置）

        Raises:
            ValueError: 設備 ID 已被註冊，或 device 缺少 connect/start/stop/disconnect
        """
        _require_lifecycle_methods(device, for_group=False)
        if device.device_id in self._registered_ids:
            raise ValueError(f"Device '{device.device_id}' already registered")
        self._standalone.append(device)
        self._registered_ids.add(device.device_id)
        logger.debug(f"已註冊獨立設備: {device.device_id}")

    def register_group(
        self,
        devices: Sequence[DeviceProtocol],
        interval: float = 1.0,
    ) -> None:
        """
        註冊設備群組

        群組內設備將由 Manager 順序呼叫 read_once() 進行讀取。

        Args:
            devices: 設備列表
            interval: 完整讀取一輪的間隔時間（秒）

        Raises:
            ValueError: 設備 ID 已被註冊，或 device 缺少 connect/disconnect/read_once/_emitter
        """
        new_ids: set[str] = set()
        for device in devices:
            _require_lifecycle_methods(device, for_group=True)
            if device.device_id in self._registered_ids or device.device_id in new_ids:
                raise ValueError(f"Device '{device.device_id}' already registered")
            new_ids.add(device.device_id)
        # DeviceGroup.devices 目前仍以 AsyncModbusDevice 具體型別保存（需呼叫 read_once / _emitter）。
        # 這裡透過 cast 串接；未來 DeviceProtocol 補齊相關欄位後可一起鬆綁（B-P2）。
        group = DeviceGroup(devices=[cast("AsyncModbusDevice", d) for d in devices], interval=interval)
        self._groups.append(group)
        self._registered_ids.update(new_ids)
        logger.debug(f"已註冊設備群組: {group.device_ids}")

    # ================ 解除註冊 ================

    async def unregister(self, device_id: str) -> bool:
        """
        解除單一獨立設備註冊

        若設備正在執行，會先 stop + disconnect（best-effort，失敗僅 warn）。
        若 device_id 屬於群組設備，不處理（請用 ``unregister_group``）。

        Args:
            device_id: 要解除註冊的設備 ID

        Returns:
            True 若成功解除，False 若設備不存在於 standalone 列表
        """
        target: DeviceProtocol | None = None
        for dev in self._standalone:
            if dev.device_id == device_id:
                target = dev
                break
        if target is None:
            logger.debug("DeviceManager.unregister: 設備 {} 不在 standalone 列表", device_id)
            return False

        if self._running:
            concrete = cast("AsyncModbusDevice", target)
            # stop/disconnect best-effort：抓 Exception 不抓 BaseException（避免吃掉 CancelledError）
            try:
                await concrete.stop()
            except Exception as e:
                logger.warning("DeviceManager.unregister: stop 失敗 device={} err={}", device_id, e)
            try:
                await concrete.disconnect()
            except Exception as e:
                logger.warning("DeviceManager.unregister: disconnect 失敗 device={} err={}", device_id, e)

        self._standalone.remove(target)
        self._registered_ids.discard(device_id)
        logger.info("DeviceManager: 已解除註冊設備 {}", device_id)
        return True

    async def unregister_group(self, device_ids: Sequence[str]) -> bool:
        """
        解除整個群組註冊

        以群組方式尋找完全匹配 ``device_ids`` 的 DeviceGroup（順序無關）。
        若正在執行，會先 group.stop()，再對每個設備 disconnect（best-effort）。
        中途 disconnect 失敗以 warn 記錄不中斷。

        Args:
            device_ids: 群組內所有設備 ID（必須與註冊時提供的完全相同）

        Returns:
            True 若成功解除，False 若找不到符合的群組
        """
        target_ids = set(device_ids)
        target_group: DeviceGroup | None = None
        for group in self._groups:
            if set(group.device_ids) == target_ids:
                target_group = group
                break
        if target_group is None:
            logger.debug("DeviceManager.unregister_group: 找不到符合的群組 {}", list(device_ids))
            return False

        if self._running:
            try:
                await target_group.stop()
            except Exception as e:
                logger.warning("DeviceManager.unregister_group: group.stop 失敗 err={}", e)

            # 逐台 disconnect 並行執行；例外在 _disconnect_one 內被吞為 warning，
            # CancelledError 不吃（向上拋以保留取消語意）。因此 gather 可用
            # return_exceptions=False（正常流程下不會有例外到達 gather）。
            async def _disconnect_one(dev: "AsyncModbusDevice") -> None:
                try:
                    await dev.disconnect()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(
                        "DeviceManager.unregister_group: disconnect 失敗 device={} err={}",
                        dev.device_id,
                        e,
                    )

            await asyncio.gather(
                *(_disconnect_one(d) for d in target_group.devices),
                return_exceptions=False,
            )

        self._groups.remove(target_group)
        for did in target_group.device_ids:
            self._registered_ids.discard(did)
        logger.info("DeviceManager: 已解除註冊設備群組 {}", target_group.device_ids)
        return True

    # ================ 生命週期 ================

    async def _on_start(self) -> None:
        """
        啟動所有設備

        獨立設備將各自啟動 read_loop，群組設備將啟動順序讀取循環。
        單一設備的連線/啟動失敗不會阻止其他設備，失敗的設備保留在註冊表，
        由其內部背景邏輯自動重試（或下次 start 時重連）。

        ``asyncio.CancelledError`` 保留原語意向上傳播；其他 Exception 僅記 warn。
        """
        if self._running:
            return

        self._running = True

        # lifecycle 方法（connect / start）尚未納入 DeviceProtocol → cast（追蹤 B-P2）
        async def _start_standalone(device: "DeviceProtocol") -> None:
            concrete = cast("AsyncModbusDevice", device)
            await _safe_device_step(concrete.connect(), device_id=device.device_id, action="connect")
            # connect 失敗仍要 start：read_loop 內部會背景重連。
            # start 失敗吞掉 + warn（expected_exc=() 讓所有 Exception 帶 stack）
            # 以維持「單台失敗不擋其他」語意。
            await _safe_device_step(concrete.start(), device_id=device.device_id, action="start", expected_exc=())

        async def _prepare_group_device(device: "DeviceProtocol") -> None:
            concrete = cast("AsyncModbusDevice", device)
            await _safe_device_step(concrete.connect(), device_id=device.device_id, action="connect")
            # 即使 connect 失敗也要啟動 event emitter（後續 read_once 仍可能觸發事件）
            await _safe_device_step(
                concrete.ensure_event_loop_started(),
                device_id=device.device_id,
                action="ensure_event_loop_started",
                expected_exc=(),
            )

        # 若啟動過程被 cancel 中斷，_running 需 rollback 避免卡在 True 狀態
        # （否則後續 start() 會被 `if self._running: return` 跳過）。用 try/finally
        # 明確表達 rollback 意圖，避免 `except BaseException` 的歧義。
        startup_completed = False
        try:
            await _gather_per_device_with_cancel(
                self._standalone,
                _start_standalone,
                failure_msg="設備 {} start 失敗，保留在註冊表等下次重試: {}",
            )

            for group in self._groups:
                await _gather_per_device_with_cancel(
                    group.devices,
                    _prepare_group_device,
                    failure_msg="群組設備 {} 準備失敗（保留在群組中）: {}",
                )
                group.start()
            startup_completed = True
        finally:
            if not startup_completed:
                self._running = False

        logger.info(
            "DeviceManager 已啟動: {} 個獨立設備, {} 個群組",
            len(self._standalone),
            len(self._groups),
        )

    async def _on_stop(self) -> None:
        """
        停止所有設備

        停止所有讀取循環並斷開連線。對每個設備採 per-device try/except，
        單一設備 stop/disconnect 失敗不會阻止其他設備收尾；
        ``asyncio.CancelledError`` 保留原語意向上傳播。
        """
        if not self._running:
            return

        self._running = False

        async def _stop_standalone(device: "DeviceProtocol") -> None:
            concrete = cast("AsyncModbusDevice", device)
            await _safe_device_step(concrete.stop(), device_id=device.device_id, action="stop", expected_exc=())
            await _safe_device_step(concrete.disconnect(), device_id=device.device_id, action="disconnect")

        await _gather_per_device_with_cancel(self._standalone, _stop_standalone, failure_msg="設備 {} 收尾失敗: {}")

        async def _stop_group_device(device: "DeviceProtocol") -> None:
            concrete = cast("AsyncModbusDevice", device)
            await _safe_device_step(
                concrete.ensure_event_loop_stopped(),
                device_id=device.device_id,
                action="ensure_event_loop_stopped",
                expected_exc=(),
            )
            await _safe_device_step(concrete.disconnect(), device_id=device.device_id, action="disconnect")

        for group in self._groups:
            try:
                await group.stop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("群組 {} stop 失敗: {}", group.device_ids, e)

            await _gather_per_device_with_cancel(
                group.devices, _stop_group_device, failure_msg="群組設備 {} 收尾失敗: {}"
            )

        logger.info("DeviceManager 已停止")

    # ================ 屬性 ================

    @property
    def is_running(self) -> bool:
        """管理器是否運行中"""
        return self._running

    @property
    def standalone_count(self) -> int:
        """獨立設備數量"""
        return len(self._standalone)

    @property
    def group_count(self) -> int:
        """設備群組數量"""
        return len(self._groups)

    @property
    def all_devices(self) -> list[DeviceProtocol]:
        """
        取得所有設備

        返回獨立設備與群組設備的合併列表。

        Returns:
            所有設備的列表（DeviceProtocol 視角）
        """
        devices: list[DeviceProtocol] = list(self._standalone)
        for group in self._groups:
            devices.extend(group.devices)
        return devices

    @property
    def groups(self) -> list[DeviceGroup]:
        """取得所有設備群組"""
        return list(self._groups)

    def __repr__(self) -> str:
        return f"<DeviceManager standalone={self.standalone_count} groups={self.group_count} running={self.is_running}>"
