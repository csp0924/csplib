# =============== Manager Data Tests - Upload Overflow ===============
#
# 驗證當底層 uploader.enqueue 回傳 False（容量滿、最舊資料被 popleft 丟棄）時，
# ``DataUploadManager`` 不可 commit ON_CHANGE dedup state 與 legacy 節流時戳。
#
# Bug 背景：
#   ``MongoBatchUploader.enqueue`` 在底層 ``BatchQueue`` 滿時會悄悄 popleft
#   最舊資料，但回傳 None。``DataUploadManager._safe_enqueue`` 只看「有沒有
#   raise」，會把 silent drop 當成功；下次相同 payload 被 ON_CHANGE 去重吞掉、
#   legacy save_interval 也因為 ``last_save_time`` 已 commit 而不再寫。
#
# 修復後 contract（與 ``MongoBatchUploader.enqueue`` 對齊）：
#   - ``BatchUploader.enqueue`` 回傳 bool，False 代表 caller 必須視同失敗
#   - ``DataUploadManager`` 在 ``_safe_enqueue`` 回 False 時不得更新
#     ``last_result`` / ``last_save_time`` / ``last_shape_cache``

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.manager.data.targets import UploadTarget, WritePolicy
from csp_lib.manager.data.upload import DataUploadManager


class MockDevice:
    """輕量 device 替身，提供 on/emit。"""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._handlers: dict[str, list] = {}

    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)

        def cancel() -> None:
            if event in self._handlers and handler in self._handlers[event]:
                self._handlers[event].remove(handler)

        return cancel

    async def emit(self, event: str, payload) -> None:
        for handler in list(self._handlers.get(event, [])):
            await handler(payload)


class DroppingUploader:
    """BatchUploader 替身：可依序回傳預設的 bool 結果模擬 enqueue 接受 / 丟棄。"""

    def __init__(self, results: list[bool]) -> None:
        self.register_collection = MagicMock()
        self._results = list(results)
        self.calls: list[tuple[str, dict]] = []
        # 暴露成 AsyncMock 介面以便 call_count 等斷言；但 side_effect 走自家 list
        self.enqueue = AsyncMock(side_effect=self._enqueue_impl)

    async def _enqueue_impl(self, collection: str, document: dict) -> bool:
        self.calls.append((collection, document))
        if not self._results:
            return True
        return self._results.pop(0)


def _read_payload(device_id: str, values: dict) -> ReadCompletePayload:
    return ReadCompletePayload(
        device_id=device_id,
        values=values,
        duration_ms=10.0,
        timestamp=datetime.now(timezone.utc),
    )


def summary_transform(values: dict) -> dict:
    return {"collection_kind": "summary", "value": values.get("v")}


# ============================================================
# ON_CHANGE 不可在 silent drop 上 commit dedup state
# ============================================================


class TestOnChangeRespectsDropSignal:
    async def test_on_change_does_not_dedup_when_drop_signalled(self) -> None:
        """第一次 enqueue 被 silent drop（回 False），同樣 payload 第二次仍須再試。"""
        uploader = DroppingUploader(results=[False, True])
        manager = DataUploadManager(uploader)
        device = MockDevice("dev")

        manager.configure(
            device.device_id,
            outputs=[UploadTarget(collection="c", transform=summary_transform, policy=WritePolicy.ON_CHANGE)],
        )
        manager.subscribe(device)

        payload = _read_payload("dev", {"v": 42})

        await device.emit(EVENT_READ_COMPLETE, payload)
        await device.emit(EVENT_READ_COMPLETE, payload)

        # 第二次必須再進 enqueue（如果 dedup state 被誤 commit，會剩 1 次）
        assert uploader.enqueue.call_count == 2

    async def test_on_change_commits_state_only_on_true(self) -> None:
        """連續 True 後相同 payload 應被去重吞掉，確保去重邏輯本身沒被破壞。"""
        uploader = DroppingUploader(results=[True, True])
        manager = DataUploadManager(uploader)
        device = MockDevice("dev")

        manager.configure(
            device.device_id,
            outputs=[UploadTarget(collection="c", transform=summary_transform, policy=WritePolicy.ON_CHANGE)],
        )
        manager.subscribe(device)

        payload = _read_payload("dev", {"v": 7})

        await device.emit(EVENT_READ_COMPLETE, payload)
        await device.emit(EVENT_READ_COMPLETE, payload)

        # 第一次成功 commit dedup state，第二次相同 payload 被去重吞掉
        assert uploader.enqueue.call_count == 1


# ============================================================
# Legacy save_interval 不可在 silent drop 上 commit last_save_time
# ============================================================


class TestLegacyThrottleRespectsDropSignal:
    async def test_legacy_throttle_retries_when_drop_signalled(self) -> None:
        """節流窗內若上次 enqueue 被丟棄，下一次 read 仍須再試。"""
        uploader = DroppingUploader(results=[False, True])
        manager = DataUploadManager(uploader)
        device = MockDevice("dev")

        manager.configure(device.device_id, "c", save_interval=60)
        manager.subscribe(device)

        payload = _read_payload("dev", {"v": 1})

        fake_time = [1000.0]
        with patch("csp_lib.manager.data.upload.time.monotonic", side_effect=lambda: fake_time[0]):
            await device.emit(EVENT_READ_COMPLETE, payload)
            # 仍在節流窗內，但上次 silent drop 沒 commit last_save_time
            fake_time[0] += 1.0
            await device.emit(EVENT_READ_COMPLETE, payload)

        assert uploader.enqueue.call_count == 2
