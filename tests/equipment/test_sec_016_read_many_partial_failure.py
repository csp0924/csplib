"""SEC-016: GroupReader.read_many() 並行路徑的部分失敗處理

設計決策：`read_many()` 的並行路徑（max_concurrent_reads > 1）目前使用
`asyncio.gather(*tasks)` 不帶 return_exceptions，導致任一群組失敗會
raise 整批讀取 → 所有成功群組的結果也被丟棄。

修復：改為 `asyncio.gather(*tasks, return_exceptions=True)` + 逐結果檢查：
- 成功結果：merge 進 merged dict
- Exception 結果：log warning 但不中斷
- CancelledError：必須正常傳播（不被吞），否則 lifecycle 停機會卡住

修復前：第一個 group 成功、第二個 raise CommunicationError → 整批 raise
→ 第一個 group 的成功結果丟失。

本檔案的每個測試在未修 source 前皆應 FAIL（部分失敗測試）或 PASS（cancel 測試
取決於現況）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from csp_lib.core.errors import CommunicationError
from csp_lib.equipment.core.point import ReadPoint
from csp_lib.equipment.transport.base import ReadGroup
from csp_lib.equipment.transport.reader import GroupReader
from csp_lib.modbus import UInt16


class TestReadManyPartialFailure:
    """GroupReader.read_many() 並行路徑對部分失敗的處理（SEC-016）"""

    async def test_partial_failure_keeps_successful_results(self):
        """
        SEC-016: 兩個 group 並行讀取，一成功一失敗 → 應回傳成功的部分，不 raise。

        修復前：asyncio.gather 無 return_exceptions → 整批失敗 → 成功 group 丟失。
        修復後：return_exceptions=True → 成功結果 merge 進 dict，失敗僅 log。
        """
        # 建立 parallel reader（max_concurrent_reads=3，走並行路徑）
        client = AsyncMock()

        # side_effect 會讓兩個 call 分別得到不同結果
        # 第一次 call → 成功回傳 [100]
        # 第二次 call → 拋 CommunicationError
        call_count = [0]

        async def read_holding_registers(addr, count, unit_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return [100]
            raise CommunicationError("device_x", "timeout")

        client.read_holding_registers.side_effect = read_holding_registers

        reader = GroupReader(client=client, max_concurrent_reads=3)

        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        p2 = ReadPoint(name="b", address=200, data_type=UInt16())
        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))
        group2 = ReadGroup(function_code=3, start_address=200, count=1, points=(p2,))

        # 修復前：raise CommunicationError；修復後：回傳 {"a": 100}
        result = await reader.read_many([group1, group2])

        # 關鍵驗證：成功 group 的結果應保留
        assert "a" in result, f"成功 group 的結果應保留，實際 result={result!r}"
        assert result["a"] == 100
        # 失敗 group 的 key 不應出現
        assert "b" not in result

    async def test_partial_failure_does_not_raise(self):
        """
        SEC-016: 部分群組失敗不應讓整個 read_many raise。

        修復前：raise CommunicationError
        修復後：return 含成功結果的 dict
        """
        client = AsyncMock()
        call_count = [0]

        async def read_holding_registers(addr, count, unit_id):
            call_count[0] += 1
            if call_count[0] == 1:
                raise CommunicationError("device_x", "timeout")
            return [200]

        client.read_holding_registers.side_effect = read_holding_registers

        reader = GroupReader(client=client, max_concurrent_reads=3)

        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        p2 = ReadPoint(name="b", address=200, data_type=UInt16())
        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))
        group2 = ReadGroup(function_code=3, start_address=200, count=1, points=(p2,))

        # 修復前：raise；修復後：不 raise，回傳 dict
        try:
            result = await reader.read_many([group1, group2])
        except CommunicationError as e:
            pytest.fail(f"read_many 不應因單 group 失敗而 raise：{e}")

        # 第二個 group 成功的結果應保留
        assert "b" in result, f"成功 group 的結果應保留，實際 result={result!r}"
        assert result["b"] == 200

    async def test_all_groups_fail_returns_empty_dict(self):
        """
        SEC-016: 所有群組都失敗 → 回傳空 dict，不 raise。

        修復前：raise 第一個遇到的 exception
        修復後：所有都 log 為 warning，回傳 {}
        """
        client = AsyncMock()
        client.read_holding_registers.side_effect = CommunicationError("device_x", "timeout")

        reader = GroupReader(client=client, max_concurrent_reads=3)

        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        p2 = ReadPoint(name="b", address=200, data_type=UInt16())
        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))
        group2 = ReadGroup(function_code=3, start_address=200, count=1, points=(p2,))

        # 修復前：raise；修復後：回傳空 dict
        result = await reader.read_many([group1, group2])

        assert result == {}, f"所有 group 都失敗應回傳空 dict，實際 {result!r}"

    # ─── regression guard：全部成功仍正常合併 ───

    async def test_all_groups_succeed_merges_normally(self):
        """SEC-016 regression guard: 全部成功時，merged dict 應包含所有 key。"""
        client = AsyncMock()
        client.read_holding_registers.side_effect = [[111], [222]]

        reader = GroupReader(client=client, max_concurrent_reads=3)

        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        p2 = ReadPoint(name="b", address=200, data_type=UInt16())
        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))
        group2 = ReadGroup(function_code=3, start_address=200, count=1, points=(p2,))

        result = await reader.read_many([group1, group2])

        assert result == {"a": 111, "b": 222}


class TestReadManyCancellation:
    """GroupReader.read_many() 對 CancelledError 的傳播（SEC-016）"""

    async def test_cancelled_error_propagates(self):
        """
        SEC-016: 外部 cancel read_many 的任務 → CancelledError 應正常傳播。

        若修復實作將所有 exception 都當 warning 吞掉（不分 CancelledError），
        會阻塞 lifecycle 正常停機。此測試確保 CancelledError 不被吞。

        注意：此測試在修復前可能 PASS（因為原始 gather 沒吞 CancelledError），
        修復時需保留此行為。
        """
        client = AsyncMock()

        # 模擬 read 會永遠掛起 → 讓 cancel 有機會發生
        async def hang_forever(*args, **kwargs):
            await asyncio.sleep(10)

        client.read_holding_registers.side_effect = hang_forever

        reader = GroupReader(client=client, max_concurrent_reads=3)

        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))

        # 起一個 task 跑 read_many，然後 cancel 它
        task = asyncio.create_task(reader.read_many([group1]))
        await asyncio.sleep(0.01)  # 讓 task 進入 hang
        task.cancel()

        # CancelledError 應從 task 傳播出來
        with pytest.raises(asyncio.CancelledError):
            await task
