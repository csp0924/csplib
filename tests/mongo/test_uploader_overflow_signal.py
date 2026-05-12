# =============== Mongo Tests - Uploader 溢位訊號 ===============
#
# 驗證 ``MongoBatchUploader.enqueue`` 在底層 ``BatchQueue`` 容量已滿、
# 被迫 popleft 丟棄最舊資料時，必須回傳 ``False`` 讓上層感知到 silent drop。
#
# Bug 背景：
#   原本 ``enqueue`` 簽名為 ``-> None``，把 ``BatchQueue.enqueue`` 的 bool 結果
#   丟掉，導致 ``DataUploadManager._safe_enqueue`` 無從得知資料是否實際進入
#   queue。一旦 queue 達 ``max_queue_size``，最舊資料會被 ``popleft`` 丟棄，
#   但呼叫者仍視為「成功」，於是 ON_CHANGE dedup state / save_interval 節流
#   時戳會在丟棄資料的當下被 commit，造成下次相同 payload 被去重吞掉 →
#   silent corruption。
#
# 修復後 contract：
#   - ``enqueue`` 必須回 ``bool``
#   - True = document 安全進入 queue（未發生 eviction）
#   - False = queue 已滿、最舊資料被 popleft 丟棄

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.uploader import MongoBatchUploader


@pytest.mark.asyncio
async def test_enqueue_returns_true_when_queue_has_room() -> None:
    """正常情況下 enqueue 必須回傳 True（document 安全入隊）。"""
    mock_db = MagicMock()
    uploader = MongoBatchUploader(mock_db, UploaderConfig(max_queue_size=10))
    uploader.register_collection("col")

    result = await uploader.enqueue("col", {"v": 1})

    assert result is True


@pytest.mark.asyncio
async def test_enqueue_returns_false_on_queue_overflow() -> None:
    """queue 達 max_queue_size 後再 enqueue，必須回 False 通知 caller 有資料被丟棄。"""
    mock_db = MagicMock()
    # max_queue_size=2 + batch_size_threshold 設大值避免 _threshold_event 干擾
    uploader = MongoBatchUploader(
        mock_db,
        UploaderConfig(max_queue_size=2, batch_size_threshold=999),
    )
    uploader.register_collection("col")

    # 填滿 queue
    assert await uploader.enqueue("col", {"i": 1}) is True
    assert await uploader.enqueue("col", {"i": 2}) is True

    # 已滿，下一筆會把最舊資料 popleft → False
    result = await uploader.enqueue("col", {"i": 3})

    assert result is False
    # 仍維持 max_queue_size 筆，且最舊那筆 ({"i":1}) 已被丟棄
    assert uploader._queues["col"].size_sync() == 2


@pytest.mark.asyncio
async def test_enqueue_auto_register_returns_true() -> None:
    """未預先 register 也能 enqueue，且回 True。"""
    mock_db = MagicMock()
    uploader = MongoBatchUploader(mock_db, UploaderConfig(max_queue_size=10))

    result = await uploader.enqueue("auto_col", {"x": 1})

    assert result is True
    assert "auto_col" in uploader._queues
