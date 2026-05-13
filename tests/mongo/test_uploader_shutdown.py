"""
MongoBatchUploader.stop() 關機保證測試 (H3 — closed-loop probe report)

Bug 背景：
- 當 Mongo 在 ``stop()`` 時不可用，``_flush_loop`` 停止分支只跑一次
  ``flush_all()``。失敗時 ``_handle_write_failure`` 會把 documents 放回 queue
  並印 "重試 N/M" WARNING，接著 loop ``break`` 結束 — documents 永遠留在記憶體
  中，程序結束後 silent data loss。
- 同時 WARNING log 對 operator 是誤導訊息（沒有任何後續重試會發生）。

修復目標（patch-level，不改 public API）：
- stop 分支應 bounded retry ``flush_all()``（預設 3 次）讓暫時性故障有機會恢復。
- 全部失敗後必須以 ERROR-level log 顯示每個 collection 還剩多少筆未落庫，
  讓 operator 可以辨認資料遺失規模（而不是被 "重試 1/2" WARNING 誤導）。

本檔案測試覆蓋：
- 失敗到底 → 必須有 ERROR log 標明 lost docs 計數
- 暫時性失敗 → 重試成功後 queue 為空、無 ERROR log
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.core.logging.capture import LogCapture
from csp_lib.mongo.config import UploaderConfig
from csp_lib.mongo.uploader import MongoBatchUploader
from csp_lib.mongo.writer import WriteResult


class TestStopGuaranteesNoSilentLoss:
    """
    stop() 必須保證：要麼資料落庫，要麼以 ERROR log 顯式標明遺失。
    """

    def _make_uploader(
        self,
        write_result: WriteResult | AsyncMock | None = None,
        flush_interval: int = 10,
    ) -> MongoBatchUploader:
        mock_db = MagicMock()
        config = UploaderConfig(
            flush_interval=flush_interval,
            batch_size_threshold=1000,  # 拉高，避免 enqueue 階段就 flush
            max_queue_size=10000,
            max_retry_count=2,
        )
        uploader = MongoBatchUploader(mock_db, config)
        uploader._writer = MagicMock()
        if isinstance(write_result, AsyncMock):
            uploader._writer.write_batch = write_result
        else:
            uploader._writer.write_batch = AsyncMock(
                return_value=write_result or WriteResult(success=False, error_message="mongo down"),
            )
        return uploader

    @pytest.mark.asyncio
    async def test_stop_with_persistent_failure_emits_error_with_lost_count(self) -> None:
        """
        H3 核心：當 Mongo 持續不可用時，stop() 必須以 ERROR-level log 標明
        每個 collection 還剩多少筆未落庫資料。

        修復前：
        - stop 分支只 flush 一次 → 失敗 → _handle_write_failure restore 回 queue +
          印 "重試 1/2" WARNING（誤導 operator） → break 退出
        - 沒有任何 ERROR log 告知 operator 資料其實沒寫進去
        → 本測試 FAIL（找不到 ERROR + lost count）

        修復後：
        - stop 分支 bounded retry flush_all() 後仍失敗 → emit ERROR log
          內容含具體筆數 + collection 名稱
        → 本測試 PASS
        """
        uploader = self._make_uploader(WriteResult(success=False, error_message="mongo down"))
        # 預先塞 300 筆，模擬 sandbox H3 scenario
        for i in range(300):
            await uploader.enqueue("metrics", {"i": i})

        # LogCapture 攔截 loguru 輸出
        with LogCapture(level="ERROR") as cap:
            uploader.start()
            # 給 _flush_loop 一點時間進入 wait
            await asyncio.sleep(0.05)
            await uploader.stop()

        error_messages = [rec.message for rec in cap.records if rec.level == "ERROR"]
        joined = "\n".join(error_messages)

        # 必須有任意 ERROR-level log 提及具體未落庫筆數（300）
        assert "300" in joined, f"stop() 在 Mongo 不可用時必須以 ERROR log 標明未落庫筆數，實際 ERROR log:\n{joined}"
        # 並且 message 要明確指向 'metrics' collection（避免只說「丟失」沒指明哪個 collection）
        assert "metrics" in joined, f"ERROR log 必須指明哪個 collection 有資料遺失，實際 ERROR log:\n{joined}"

    @pytest.mark.asyncio
    async def test_stop_with_transient_failure_eventually_persists(self) -> None:
        """
        暫時性故障 — 前幾次 write_batch 失敗、第 N 次成功。
        bounded retry 應該讓資料最終落庫，queue 清空且不噴 ERROR。

        修復前：stop 分支只跑一次 flush_all()，第一次失敗就 break →
        queue 永遠不空 → FAIL（assert queue empty 失敗）

        修復後：bounded retry 後成功 → PASS
        """
        # 第 1 次 fail、第 2 次 success
        call_count = {"n": 0}

        async def flaky_write(collection_name: str, docs: list[dict]) -> WriteResult:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return WriteResult(success=False, error_message="transient")
            return WriteResult(success=True, inserted_count=len(docs))

        mock_write = AsyncMock(side_effect=flaky_write)
        uploader = self._make_uploader(write_result=mock_write)

        for i in range(50):
            await uploader.enqueue("metrics", {"i": i})

        with LogCapture(level="WARNING") as cap:
            uploader.start()
            await asyncio.sleep(0.05)
            await uploader.stop()

        # 暫時性失敗應在 bounded retry 內恢復 → queue 為空
        assert await uploader._queues["metrics"].size() == 0, (
            "暫時性 Mongo 故障應在 stop 的 bounded retry 內成功，queue 應為空"
        )
        # 至少呼叫 2 次（1 次失敗 + 1 次重試成功）
        assert call_count["n"] >= 2, f"應該有 retry，實際 write_batch 呼叫次數={call_count['n']}"

        # 重試成功路徑不應留下任何 ERROR log（lost-count ERROR 是 silent loss 訊號，
        # transient failure 順利恢復後不該誤觸發；防止未來改動把暫時性失敗誤判成 lost）
        error_records = [rec for rec in cap.records if rec.level == "ERROR"]
        assert not error_records, (
            "暫時性失敗在 bounded retry 內恢復後不應 emit ERROR log，"
            f"實際 ERROR records: {[(r.level, r.message) for r in error_records]}"
        )
