# =============== Equipment Transport Tests - Rotating Slot Failure Recovery ===============
#
# 驗證 ReadScheduler 在 rotating slot 讀取失敗時不會 silently 跳過該 slot。
#
# Bug 背景：
#   原本 ReadScheduler.get_next_groups() 在被呼叫的瞬間就推進 _rotating_index，
#   而 GroupReader.read_many() 對個別 group 失敗會 swallow 並回傳 partial dict。
#   `_read_all` 沒有偵測這種「rotating slot 整個失敗」的情況，導致該 slot
#   要等下一整輪 K-cycle 才會被重訪 — silent data staleness。
#
# 修法：
#   1. ReadScheduler 新增 `rollback_index()` 與 `get_next_groups_with_rotating()`。
#   2. AsyncModbusDevice._read_all 在 read_many 回傳後檢查 rotating slot 預期的
#      點位名是否齊全，若有缺失就 rollback rotating_index → 下個 cycle 重試。

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.core import ReadPoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.transport.base import ReadGroup
from csp_lib.equipment.transport.scheduler import ReadScheduler
from csp_lib.modbus import UInt16

# ======================== Scheduler-Level API Tests ========================


def _g(start: int, points: tuple[ReadPoint, ...] = ()) -> ReadGroup:
    """建立簡單 ReadGroup"""
    return ReadGroup(function_code=3, start_address=start, count=1, points=points)


class TestRollbackIndex:
    """ReadScheduler.rollback_index() 行為"""

    def test_rollback_after_advance_returns_to_same_slot(self):
        """advance 過一次後 rollback，下一次 get 應回到原本的 slot"""
        rot_a = [_g(100)]
        rot_b = [_g(200)]
        rot_c = [_g(300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        # 第一次 advance：拿到 rot_a，index 推到 1
        first = scheduler.get_next_groups()
        assert first == rot_a
        assert scheduler.current_rotating_index == 1

        # rollback：index 應回到 0
        scheduler.rollback_index()
        assert scheduler.current_rotating_index == 0

        # 下次 get 再次回傳 rot_a（同一個 slot 被重試）
        again = scheduler.get_next_groups()
        assert again == rot_a

    def test_rollback_at_index_zero_wraps_to_last(self):
        """index=0 時 rollback 應回繞到最後一個 slot（剛剛 advance 完一輪）"""
        rot_a = [_g(100)]
        rot_b = [_g(200)]
        rot_c = [_g(300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        # advance 三次後 index 回到 0
        scheduler.get_next_groups()  # rot_a, idx -> 1
        scheduler.get_next_groups()  # rot_b, idx -> 2
        scheduler.get_next_groups()  # rot_c, idx -> 0
        assert scheduler.current_rotating_index == 0

        # 剛剛讀的是 rot_c (slot 2)，rollback 應回到 2
        scheduler.rollback_index()
        assert scheduler.current_rotating_index == 2

        # 下次 get 應再讀 rot_c
        assert scheduler.get_next_groups() == rot_c

    def test_rollback_without_rotating_is_safe(self):
        """無 rotating 群組時 rollback 不應拋出異常"""
        scheduler = ReadScheduler(always_groups=[_g(0)])
        # 不應拋異常
        scheduler.rollback_index()
        assert scheduler.current_rotating_index == 0

    def test_rollback_with_single_rotating_slot(self):
        """只有一個 rotating slot 時 rollback 之後 index 仍為 0"""
        scheduler = ReadScheduler(rotating_groups=[[_g(100)]])
        scheduler.get_next_groups()
        # 1 個 slot：advance 後 index = 0，rollback 後仍為 0
        scheduler.rollback_index()
        assert scheduler.current_rotating_index == 0


class TestGetNextGroupsWithRotating:
    """ReadScheduler.get_next_groups_with_rotating() 行為"""

    def test_returns_tuple_of_all_and_rotating(self):
        """回傳 (all_groups, rotating_slice) 兩個 list"""
        always_g = _g(0)
        rot_a = [_g(100), _g(110)]
        rot_b = [_g(200)]
        scheduler = ReadScheduler(always_groups=[always_g], rotating_groups=[rot_a, rot_b])

        all_groups, rotating = scheduler.get_next_groups_with_rotating()

        assert all_groups == [always_g, *rot_a]
        assert rotating == rot_a

    def test_advances_index(self):
        """呼叫後 rotating_index 應推進（與 get_next_groups 行為一致）"""
        rot_a = [_g(100)]
        rot_b = [_g(200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        scheduler.get_next_groups_with_rotating()
        assert scheduler.current_rotating_index == 1

    def test_no_rotating_returns_empty_rotating_list(self):
        """無 rotating 時 rotating slice 為空列表"""
        always_g = _g(0)
        scheduler = ReadScheduler(always_groups=[always_g])

        all_groups, rotating = scheduler.get_next_groups_with_rotating()

        assert all_groups == [always_g]
        assert rotating == []


# ======================== Device-Level Integration Tests ========================


@pytest.fixture
def device_config() -> DeviceConfig:
    return DeviceConfig(
        device_id="rotating_test",
        unit_id=1,
        address_offset=0,
        read_interval=0.1,
        disconnect_threshold=3,
    )


@pytest.fixture
def always_points() -> list[ReadPoint]:
    return [ReadPoint(name="always_power", address=100, data_type=UInt16())]


@pytest.fixture
def rotating_points() -> list[list[ReadPoint]]:
    """3 個 rotating slot，每個 slot 一個獨立點位"""
    return [
        [ReadPoint(name="sbms1_soc", address=200, data_type=UInt16())],
        [ReadPoint(name="sbms2_soc", address=300, data_type=UInt16())],
        [ReadPoint(name="sbms3_soc", address=400, data_type=UInt16())],
    ]


class TestRotatingSlotFailureRollback:
    """AsyncModbusDevice 對 rotating slot 失敗的回滾行為"""

    async def test_rotating_index_does_not_advance_on_full_failure(
        self,
        device_config: DeviceConfig,
        always_points: list[ReadPoint],
        rotating_points: list[list[ReadPoint]],
    ):
        """rotating slot 完全失敗（read_many 回傳 dict 不含 slot 內任何點位名）→
        下次 _read_all 應重訪同一個 slot，而非跳到下一個。"""
        client = AsyncMock()
        device = AsyncModbusDevice(
            config=device_config,
            client=client,
            always_points=always_points,
            rotating_points=rotating_points,
        )

        # 攔截 _reader.read_many：第一次模擬 rotating slot 全失敗
        # （回傳只含 always 點位，rotating slot 的 point name 缺席）
        call_log: list[tuple[int, ...]] = []

        async def fake_read_many(groups, *_args, **_kwargs):
            # 紀錄每次傳入的 group start addresses
            starts = tuple(g.start_address for g in groups)
            call_log.append(starts)
            # 模擬：只回 always 點位，rotating 點位全失敗 swallow
            return {"always_power": 42}

        device._reader.read_many = fake_read_many  # type: ignore[assignment]

        # 第一次 _read_all：應讀 always + rotating[0]（slot 0 → sbms1_soc）
        await device._read_all()
        assert call_log[0] == (100, 200), f"first call should hit always(100) + slot0(200), got {call_log[0]}"

        # 關鍵驗證：rotating slot 失敗 → index 應回滾，下次再讀同一 slot (200)
        # 修復前：index 已推到 1，下次會讀 slot1 (300) → bug
        # 修復後：index 回滾到 0，下次再讀 slot0 (200)
        await device._read_all()
        assert call_log[1] == (100, 200), (
            f"rotating slot 0 failed → next call should retry slot 0 (start=200), "
            f"got {call_log[1]}（若為 (100, 300) 則 bug 未修：index 推進但 slot 沒拿到資料）"
        )

    async def test_rotating_advances_normally_on_success(
        self,
        device_config: DeviceConfig,
        always_points: list[ReadPoint],
        rotating_points: list[list[ReadPoint]],
    ):
        """happy path：rotating slot 全部成功時，index 正常推進。"""
        client = AsyncMock()
        device = AsyncModbusDevice(
            config=device_config,
            client=client,
            always_points=always_points,
            rotating_points=rotating_points,
        )

        call_log: list[tuple[int, ...]] = []

        async def fake_read_many(groups, *_args, **_kwargs):
            starts = tuple(g.start_address for g in groups)
            call_log.append(starts)
            # 所有 group 都成功：回傳所有預期的點位
            result: dict[str, int] = {}
            for g in groups:
                for p in g.points:
                    result[p.name] = 1
            return result

        device._reader.read_many = fake_read_many  # type: ignore[assignment]

        # 三次成功讀取應依序訪問 slot 0 → slot 1 → slot 2
        await device._read_all()
        await device._read_all()
        await device._read_all()

        assert call_log[0] == (100, 200), f"call 0: always + slot0, got {call_log[0]}"
        assert call_log[1] == (100, 300), f"call 1: always + slot1, got {call_log[1]}"
        assert call_log[2] == (100, 400), f"call 2: always + slot2, got {call_log[2]}"

    async def test_rotating_failed_slot_retried_next_cycle_then_advance(
        self,
        device_config: DeviceConfig,
        always_points: list[ReadPoint],
        rotating_points: list[list[ReadPoint]],
    ):
        """slot 0 失敗 → slot 0 重試成功 → 再下一輪推進到 slot 1。"""
        client = AsyncMock()
        device = AsyncModbusDevice(
            config=device_config,
            client=client,
            always_points=always_points,
            rotating_points=rotating_points,
        )

        call_log: list[tuple[int, ...]] = []
        attempt = {"n": 0}

        async def fake_read_many(groups, *_args, **_kwargs):
            starts = tuple(g.start_address for g in groups)
            call_log.append(starts)
            attempt["n"] += 1
            # 第 1 次：rotating slot 0 失敗（只回 always）
            # 第 2 次起：全部成功
            if attempt["n"] == 1:
                return {"always_power": 42}
            result: dict[str, int] = {}
            for g in groups:
                for p in g.points:
                    result[p.name] = 1
            return result

        device._reader.read_many = fake_read_many  # type: ignore[assignment]

        await device._read_all()  # slot0 失敗
        await device._read_all()  # slot0 重試 OK
        await device._read_all()  # 推進到 slot1

        assert call_log[0] == (100, 200), f"call 0: slot0 first attempt, got {call_log[0]}"
        assert call_log[1] == (100, 200), f"call 1: slot0 retry (rollback worked), got {call_log[1]}"
        assert call_log[2] == (100, 300), f"call 2: advance to slot1, got {call_log[2]}"

    async def test_rotating_partial_failure_within_slot_also_rolls_back(
        self,
        device_config: DeviceConfig,
    ):
        """單一 rotating slot 含多個 points，部分失敗時仍應 rollback
        （任一預期點位缺席就視為該 slot 不完整 → 重訪）"""
        client = AsyncMock()
        # 一個 slot 含兩個 point
        rotating = [
            [
                ReadPoint(name="sbms1_a", address=200, data_type=UInt16()),
                ReadPoint(name="sbms1_b", address=201, data_type=UInt16()),
            ],
            [ReadPoint(name="sbms2_a", address=300, data_type=UInt16())],
        ]
        device = AsyncModbusDevice(
            config=device_config,
            client=client,
            rotating_points=rotating,
        )

        call_log: list[tuple[int, ...]] = []

        async def fake_read_many(groups, *_args, **_kwargs):
            starts = tuple(g.start_address for g in groups)
            call_log.append(starts)
            # 第一次：只回一半的 slot0 點位 → 視為失敗
            if len(call_log) == 1:
                return {"sbms1_a": 1}  # 缺 sbms1_b
            # 第二次：完整 → 成功
            result: dict[str, int] = {}
            for g in groups:
                for p in g.points:
                    result[p.name] = 1
            return result

        device._reader.read_many = fake_read_many  # type: ignore[assignment]

        await device._read_all()  # slot0 部分失敗
        await device._read_all()  # 應重試 slot0
        await device._read_all()  # 推進到 slot1

        assert call_log[0][0] == 200, f"call 0: slot0 first, got {call_log[0]}"
        assert call_log[1][0] == 200, f"call 1: slot0 retry (partial failure rolls back), got {call_log[1]}"
        assert call_log[2][0] == 300, f"call 2: slot1, got {call_log[2]}"
