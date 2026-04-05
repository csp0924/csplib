# =============== CAN Client - python-can Implementation ===============
#
# 基於 python-can 的 CAN 客戶端實作
#
# 支援 SocketCAN、TCP 閘道器等多種介面。

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from csp_lib.can.config import CANBusConfig, CANFrame
from csp_lib.can.exceptions import CANConnectionError, CANSendError, CANTimeoutError
from csp_lib.core import get_logger

from .base import AsyncCANClientBase

logger = get_logger(__name__)


class PythonCANClient(AsyncCANClientBase):
    """
    基於 python-can 的 CAN 客戶端

    將 python-can 的阻塞 I/O 包裝為 async 介面。
    背景 listener task 持續接收訊框，按 CAN ID 分發到已訂閱的 handlers。

    使用範例::

        client = PythonCANClient(CANBusConfig(interface="socketcan", channel="can0"))
        await client.connect()
        await client.start_listener()

        cancel = client.subscribe(0x100, lambda frame: print(frame))
        await client.send(0x200, b"\\x01\\x02")

        await client.stop_listener()
        await client.disconnect()
    """

    def __init__(self, config: CANBusConfig) -> None:
        self._config = config
        self._bus: Any = None  # can.Bus instance
        self._connected = False
        self._listener_task: asyncio.Task[None] | None = None
        self._handlers: dict[int, list[Callable[[CANFrame], Any]]] = {}
        self._pending_responses: dict[int, asyncio.Future[CANFrame]] = {}

    async def connect(self) -> None:
        if self._connected:
            return
        try:
            import can

            self._bus = await asyncio.to_thread(
                can.Bus,
                interface=self._config.interface,
                channel=self._config.channel,
                bitrate=self._config.bitrate,
                receive_own_messages=self._config.receive_own_messages,
            )
            self._connected = True
            logger.info(
                "CAN 連線成功: interface={}, channel={}",
                self._config.interface,
                self._config.channel,
            )
        except ImportError as e:
            raise CANConnectionError(
                "python-can 未安裝，請使用 pip install python-can 或 pip install csp0924_lib[can]"
            ) from e
        except Exception as e:
            raise CANConnectionError(f"CAN 連線失敗: {e}") from e

    async def disconnect(self) -> None:
        await self.stop_listener()
        if self._bus is not None:
            try:
                await asyncio.to_thread(self._bus.shutdown)
            except Exception as e:
                logger.warning("CAN 斷線錯誤: {}", e)
            self._bus = None
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def start_listener(self) -> None:
        if self._listener_task is not None:
            return
        self._listener_task = asyncio.create_task(self._listen_loop(), name="can_listener")

    async def stop_listener(self) -> None:
        if self._listener_task is None:
            return
        self._listener_task.cancel()
        try:
            await self._listener_task
        except asyncio.CancelledError:
            pass
        self._listener_task = None

    def subscribe(self, can_id: int, handler: Callable[[CANFrame], Any]) -> Callable[[], None]:
        if can_id not in self._handlers:
            self._handlers[can_id] = []
        self._handlers[can_id].append(handler)

        def cancel() -> None:
            if can_id in self._handlers and handler in self._handlers[can_id]:
                self._handlers[can_id].remove(handler)

        return cancel

    async def send(self, can_id: int, data: bytes) -> None:
        if not self._connected or self._bus is None:
            raise CANSendError("CAN 未連線", can_id=can_id)
        try:
            import can

            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            await asyncio.to_thread(self._bus.send, msg)
        except CANSendError:
            raise
        except Exception as e:
            raise CANSendError(f"CAN 發送失敗: {e}", can_id=can_id) from e

    async def request(
        self,
        can_id: int,
        data: bytes,
        response_id: int,
        timeout: float = 1.0,
    ) -> CANFrame:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[CANFrame] = loop.create_future()
        self._pending_responses[response_id] = future

        try:
            await self.send(can_id, data)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as e:
            raise CANTimeoutError(f"等待 CAN ID 0x{response_id:03X} 回應逾時 ({timeout}s)", can_id=response_id) from e
        finally:
            self._pending_responses.pop(response_id, None)

    async def _listen_loop(self) -> None:
        """背景接收循環"""
        while True:
            try:
                msg = await asyncio.to_thread(self._bus.recv, 1.0)
                if msg is None:
                    continue

                frame = CANFrame(
                    can_id=msg.arbitration_id,
                    data=bytes(msg.data),
                    timestamp=msg.timestamp or time.time(),
                    is_remote=msg.is_remote_frame,
                )

                # 優先處理 request-response
                pending = self._pending_responses.get(frame.can_id)
                if pending is not None and not pending.done():
                    pending.set_result(frame)

                # 分發給訂閱者
                handlers = self._handlers.get(frame.can_id, [])
                for handler in handlers:
                    try:
                        result = handler(frame)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.opt(exception=True).warning("CAN handler 錯誤: can_id=0x{:03X}", frame.can_id)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.opt(exception=True).warning("CAN listener 錯誤")


__all__ = [
    "PythonCANClient",
]
