# =============== Manager Data Tests - Upload Fan-out ===============
#
# DataUploadManager fan-out 模式測試
#
# 測試覆蓋：
#   - UploadTarget fan-out 基本語意（1 device 多 target）
#   - Transform 多型回傳值（None / dict / list[dict] / []）
#   - WritePolicy.ON_CHANGE 去重語意
#   - WritePolicy.INTERVAL 尚未實作的 fail-fast
#   - per-target 例外隔離（transform 例外、enqueue 例外）
#   - configure() 參數互斥驗證
#   - 斷線空值記錄（ALWAYS only）
#   - subscribe / unsubscribe 清理
#   - legacy + fan-out 共存

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.equipment.device.events import (
    EVENT_READ_COMPLETE,
    DisconnectPayload,
    ReadCompletePayload,
)
from csp_lib.manager.data.targets import UploadTarget, WritePolicy
from csp_lib.manager.data.upload import DataUploadManager

# ================ 測試用 double ================


class MockDevice:
    """輕量 AsyncModbusDevice 替身，提供 on/emit。"""

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


class FakeUploader:
    """BatchUploader 替身。用 AsyncMock 追蹤 enqueue 呼叫。"""

    def __init__(self) -> None:
        self.enqueue = AsyncMock()
        self.register_collection = MagicMock()

    def calls_for(self, collection: str) -> list[dict]:
        """取得指定 collection 的所有 enqueue document。"""
        return [c.args[1] for c in self.enqueue.call_args_list if c.args[0] == collection]


# ================ 共用 transforms ================


def summary_transform(values: dict) -> dict:
    """產出單筆文件。"""
    return {"collection_kind": "summary", "value": values.get("v")}


def detail_transform(values: dict) -> dict:
    """產出另一筆單筆文件。"""
    return {"collection_kind": "detail", "raw": dict(values)}


def explode_transform(values: dict) -> list[dict]:
    """展開 values 為多筆文件（list-explode）。"""
    return [{"key": k, "value": v} for k, v in values.items()]


def none_transform(_: dict) -> None:
    """總是回傳 None（跳過）。"""
    return None


def empty_list_transform(_: dict) -> list[dict]:
    """回傳空 list（不寫入、不報錯）。"""
    return []


def raising_transform(_: dict) -> dict:
    """Transform 內拋例外。"""
    raise RuntimeError("transform boom")


# ================ 共用 helpers ================


def _read_payload(device_id: str, values: dict) -> ReadCompletePayload:
    return ReadCompletePayload(
        device_id=device_id,
        values=values,
        duration_ms=10.0,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def uploader() -> FakeUploader:
    return FakeUploader()


@pytest.fixture
def manager(uploader: FakeUploader) -> DataUploadManager:
    return DataUploadManager(uploader=uploader)


# ============================================================
# 1. fan-out basic
# ============================================================


class TestFanoutBasic:
    """一個設備綁兩個 ALWAYS target，一次讀取應 fan-out 到兩個 collection。"""

    async def test_two_targets_both_enqueued(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(collection="summary_coll", transform=summary_transform),
                UploadTarget(collection="detail_coll", transform=detail_transform),
            ],
        )
        manager.subscribe(device)

        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 42}))

        # 兩個 collection 各一次 enqueue
        summary_docs = uploader.calls_for("summary_coll")
        detail_docs = uploader.calls_for("detail_coll")
        assert len(summary_docs) == 1
        assert len(detail_docs) == 1
        assert summary_docs[0] == {"collection_kind": "summary", "value": 42}
        assert detail_docs[0] == {"collection_kind": "detail", "raw": {"v": 42}}
        assert uploader.enqueue.await_count == 2

    async def test_register_collection_called_for_each_target(self, manager: DataUploadManager, uploader: FakeUploader):
        manager.configure(
            "dev_A",
            outputs=[
                UploadTarget(collection="c1", transform=summary_transform),
                UploadTarget(collection="c2", transform=detail_transform),
            ],
        )
        called = {c.args[0] for c in uploader.register_collection.call_args_list}
        assert called == {"c1", "c2"}


# ============================================================
# 2. transform returning None → skip
# ============================================================


class TestTransformReturningNone:
    async def test_none_skips_enqueue_for_that_target(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(collection="skip_coll", transform=none_transform),
                UploadTarget(collection="ok_coll", transform=summary_transform),
            ],
        )
        manager.subscribe(device)

        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 1}))

        assert uploader.calls_for("skip_coll") == []
        assert len(uploader.calls_for("ok_coll")) == 1


# ============================================================
# 3. transform returning list[dict] → explode
# ============================================================


class TestTransformReturningList:
    async def test_list_explode_enqueues_each_doc(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[UploadTarget(collection="ex_coll", transform=explode_transform)],
        )
        manager.subscribe(device)

        await device.emit(
            EVENT_READ_COMPLETE,
            _read_payload("dev_A", {"a": 1, "b": 2, "c": 3}),
        )

        docs = uploader.calls_for("ex_coll")
        assert len(docs) == 3
        # 每筆 doc 都包含獨立的 key/value
        keys = {d["key"] for d in docs}
        assert keys == {"a", "b", "c"}


# ============================================================
# 4. transform returning empty list → no-op
# ============================================================


class TestTransformEmptyList:
    async def test_empty_list_no_enqueue_no_error(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[UploadTarget(collection="e_coll", transform=empty_list_transform)],
        )
        manager.subscribe(device)

        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 1}))

        assert uploader.calls_for("e_coll") == []
        assert uploader.enqueue.await_count == 0


# ============================================================
# 5. ON_CHANGE policy
# ============================================================


class TestOnChangePolicy:
    async def test_on_change_dedup_and_update_on_diff(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(
                    collection="oc_coll",
                    transform=summary_transform,
                    policy=WritePolicy.ON_CHANGE,
                ),
            ],
        )
        manager.subscribe(device)

        # 1st read → write
        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 1}))
        assert len(uploader.calls_for("oc_coll")) == 1

        # 2nd read with identical transform output → skip
        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 1}))
        assert len(uploader.calls_for("oc_coll")) == 1

        # 3rd read with changed output → write, cache updated
        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 2}))
        docs = uploader.calls_for("oc_coll")
        assert len(docs) == 2
        assert docs[-1] == {"collection_kind": "summary", "value": 2}

        # 4th read again with v=2 → dedup again
        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 2}))
        assert len(uploader.calls_for("oc_coll")) == 2


# ============================================================
# 6. transform raising exception → target skipped, others unaffected
# ============================================================


class TestTransformExceptionIsolation:
    async def test_transform_exception_other_target_still_runs(
        self, manager: DataUploadManager, uploader: FakeUploader, caplog
    ):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(collection="bad_coll", transform=raising_transform),
                UploadTarget(collection="good_coll", transform=summary_transform),
            ],
        )
        manager.subscribe(device)

        # 不應 propagate 例外
        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 7}))

        # bad target 無任何寫入，good target 正常寫入
        assert uploader.calls_for("bad_coll") == []
        good_docs = uploader.calls_for("good_coll")
        assert len(good_docs) == 1
        assert good_docs[0]["value"] == 7


# ============================================================
# 7. enqueue raising exception → same isolation
# ============================================================


class TestEnqueueExceptionIsolation:
    async def test_enqueue_exception_other_target_still_runs(self, uploader: FakeUploader):
        # 自訂 enqueue：對 bad_coll 拋錯，其他正常
        async def selective_enqueue(collection: str, doc: dict) -> None:
            if collection == "bad_coll":
                raise RuntimeError("enqueue boom")

        uploader.enqueue.side_effect = selective_enqueue

        manager = DataUploadManager(uploader=uploader)
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(collection="bad_coll", transform=summary_transform),
                UploadTarget(collection="good_coll", transform=detail_transform),
            ],
        )
        manager.subscribe(device)

        # 不應 propagate 例外
        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 9}))

        # 兩個 target 的 enqueue 都被呼叫（bad 失敗但被隔離）
        collections = [c.args[0] for c in uploader.enqueue.call_args_list]
        assert "bad_coll" in collections
        assert "good_coll" in collections


# ============================================================
# 8. INTERVAL policy → NotImplementedError at configure time
# ============================================================


class TestIntervalPolicyFailFast:
    def test_interval_raises_not_implemented(self, manager: DataUploadManager):
        with pytest.raises(NotImplementedError, match="INTERVAL"):
            manager.configure(
                "dev_A",
                outputs=[
                    UploadTarget(
                        collection="iv_coll",
                        transform=summary_transform,
                        policy=WritePolicy.INTERVAL,
                    ),
                ],
            )


# ============================================================
# 9. mutual exclusion validation in configure()
# ============================================================


class TestConfigureValidation:
    def test_both_collection_and_outputs_raises(self, manager: DataUploadManager):
        with pytest.raises(ValueError, match="不可同時"):
            manager.configure(
                "dev_A",
                "legacy_coll",
                outputs=[UploadTarget(collection="new_coll", transform=summary_transform)],
            )

    def test_neither_collection_nor_outputs_raises(self, manager: DataUploadManager):
        with pytest.raises(ValueError, match="必須提供"):
            manager.configure("dev_A")

    def test_empty_outputs_list_raises(self, manager: DataUploadManager):
        with pytest.raises(ValueError, match="不可為空"):
            manager.configure("dev_A", outputs=[])

    def test_configure_without_device_id_raises(self, manager: DataUploadManager):
        # device_id 是必要位置參數；漏掉 → TypeError
        with pytest.raises(TypeError):
            manager.configure()  # type: ignore[call-arg]


# ============================================================
# 10. disconnect behavior
# ============================================================


class TestDisconnectBehavior:
    async def test_always_target_with_cache_emits_null_doc(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(collection="always_coll", transform=detail_transform),
            ],
        )
        manager.subscribe(device)

        # 先讀取一次建立 shape cache
        await device.emit(
            EVENT_READ_COMPLETE,
            _read_payload("dev_A", {"a": 1, "b": 2}),
        )
        uploader.enqueue.reset_mock()

        # 斷線
        await manager._on_disconnected(DisconnectPayload(device_id="dev_A", reason="timeout", consecutive_failures=3))

        null_docs = uploader.calls_for("always_coll")
        assert len(null_docs) == 1
        # detail_transform 產出 {"collection_kind": "...", "raw": {...}}
        # nullify_nested 會把葉節點全部轉 None（含字串 "detail"）
        assert null_docs[0] == {"collection_kind": None, "raw": {"a": None, "b": None}}

    async def test_on_change_target_no_null_doc_on_disconnect(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(
                    collection="oc_coll",
                    transform=summary_transform,
                    policy=WritePolicy.ON_CHANGE,
                ),
            ],
        )
        manager.subscribe(device)

        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 1}))
        uploader.enqueue.reset_mock()

        await manager._on_disconnected(DisconnectPayload(device_id="dev_A", reason="timeout", consecutive_failures=3))

        # ON_CHANGE target 不該產出斷線空值
        assert uploader.enqueue.await_count == 0

    async def test_mixed_targets_only_always_emits_null(self, manager: DataUploadManager, uploader: FakeUploader):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[
                UploadTarget(collection="always_coll", transform=summary_transform),
                UploadTarget(
                    collection="oc_coll",
                    transform=detail_transform,
                    policy=WritePolicy.ON_CHANGE,
                ),
            ],
        )
        manager.subscribe(device)

        await device.emit(EVENT_READ_COMPLETE, _read_payload("dev_A", {"v": 5}))
        uploader.enqueue.reset_mock()

        await manager._on_disconnected(DisconnectPayload(device_id="dev_A", reason="timeout", consecutive_failures=3))

        # 只有 always_coll 收到 null doc
        assert len(uploader.calls_for("always_coll")) == 1
        assert uploader.calls_for("oc_coll") == []


# ============================================================
# 11. subscribe/unsubscribe cleanup
# ============================================================


class TestSubscribeUnsubscribeCleanup:
    async def test_unsubscribe_clears_device_targets(self, manager: DataUploadManager):
        device = MockDevice("dev_A")
        manager.configure(
            device.device_id,
            outputs=[UploadTarget(collection="c", transform=summary_transform)],
        )
        manager.subscribe(device)

        assert "dev_A" in manager._device_targets

        manager.unsubscribe(device)

        assert "dev_A" not in manager._device_targets


# ============================================================
# 12. legacy + fan-out coexistence
# ============================================================


class TestLegacyAndFanoutCoexistence:
    async def test_two_devices_legacy_and_fanout_independent(self, manager: DataUploadManager, uploader: FakeUploader):
        dev_legacy = MockDevice("dev_legacy")
        dev_fanout = MockDevice("dev_fanout")

        manager.configure(dev_legacy.device_id, "legacy_coll")
        manager.subscribe(dev_legacy)

        manager.configure(
            dev_fanout.device_id,
            outputs=[
                UploadTarget(collection="fanout_summary", transform=summary_transform),
                UploadTarget(collection="fanout_detail", transform=detail_transform),
            ],
        )
        manager.subscribe(dev_fanout)

        # 各自觸發一次 read
        await dev_legacy.emit(EVENT_READ_COMPLETE, _read_payload("dev_legacy", {"temperature": 25.5}))
        await dev_fanout.emit(EVENT_READ_COMPLETE, _read_payload("dev_fanout", {"v": 10}))

        # Legacy：以 {device_id, timestamp, **values} 形式寫入 legacy_coll
        legacy_docs = uploader.calls_for("legacy_coll")
        assert len(legacy_docs) == 1
        assert legacy_docs[0]["device_id"] == "dev_legacy"
        assert legacy_docs[0]["temperature"] == 25.5

        # Fan-out：兩個 collection 各一筆
        assert len(uploader.calls_for("fanout_summary")) == 1
        assert len(uploader.calls_for("fanout_detail")) == 1

        # 兩個設備完全獨立，legacy 不會污染 fanout collection
        assert uploader.calls_for("fanout_summary")[0] == {
            "collection_kind": "summary",
            "value": 10,
        }


# ================ enqueue 失敗後不 commit 快取 ================


class TestEnqueueFailureDoesNotPollute:
    """enqueue 失敗時，ON_CHANGE 去重與 legacy 節流狀態都不應被提前 commit。

    否則一次失敗後，下游恢復時相同的 payload 會被去重吞掉 / 節流窗內也不會
    再試，導致資料遺失。
    """

    async def test_on_change_retries_after_enqueue_failure(self) -> None:
        uploader = FakeUploader()
        manager = DataUploadManager(uploader)
        device = MockDevice("dev")

        manager.configure(
            device.device_id,
            outputs=[UploadTarget(collection="c", transform=summary_transform, policy=WritePolicy.ON_CHANGE)],
        )
        manager.subscribe(device)

        # 第 1 次 enqueue 失敗，第 2 次成功；兩次的 transform 輸出相同
        uploader.enqueue.side_effect = [RuntimeError("boom"), None]
        payload = _read_payload("dev", {"v": 42})

        await device.emit(EVENT_READ_COMPLETE, payload)
        await device.emit(EVENT_READ_COMPLETE, payload)

        # 兩次都進 enqueue（第 1 次失敗沒 commit last_result，第 2 次重試）
        assert uploader.enqueue.call_count == 2

    async def test_legacy_throttle_retries_after_enqueue_failure(self) -> None:
        uploader = FakeUploader()
        manager = DataUploadManager(uploader)
        device = MockDevice("dev")

        manager.configure(device.device_id, "c", save_interval=60)
        manager.subscribe(device)

        uploader.enqueue.side_effect = [RuntimeError("boom"), None]
        payload = _read_payload("dev", {"v": 1})

        fake_time = [1000.0]
        with patch("csp_lib.manager.data.upload.time.monotonic", side_effect=lambda: fake_time[0]):
            await device.emit(EVENT_READ_COMPLETE, payload)
            # 仍在節流窗內但第一次失敗；last_save_time 應未 commit，所以第二次還要再試
            fake_time[0] += 1.0
            await device.emit(EVENT_READ_COMPLETE, payload)

        assert uploader.enqueue.call_count == 2
