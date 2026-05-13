"""Tests for LeaderElector._watch_leader_key — 外部刪除 election key 觸發 demotion。

驗證 LeaderElector 在 leader 期間若 election key 被外部刪除（非自身 resign），
能在短時間內偵測到並觸發 demotion，而非等到 keepalive 連續失敗 ~10s。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.cluster.config import ClusterConfig, EtcdConfig
from csp_lib.cluster.election import LeaderElector

# --- Watch event helpers ---


@dataclass
class FakeWatchEvent:
    """模擬 etcetra.types.WatchEvent 的最小介面。"""

    event_type: str  # "PUT" or "DELETE"
    key: str
    value: str | None = None


def _make_config(instance_id: str = "node-1") -> ClusterConfig:
    return ClusterConfig(
        instance_id=instance_id,
        etcd=EtcdConfig(endpoints=["localhost:2379"]),
        lease_ttl=5,
        max_keepalive_failures=3,
    )


def _make_watch_queue(events: list[FakeWatchEvent]):
    """建立一個 async iterator，依序 yield 給定的 events。

    Yield 完所有事件後阻塞（模擬 etcd watch 長連線）；測試可透過 queue.put(None)
    主動結束 iterator。
    """
    queue: asyncio.Queue[FakeWatchEvent | None] = asyncio.Queue()
    for ev in events:
        queue.put_nowait(ev)

    async def _iter():
        while True:
            ev = await queue.get()
            if ev is None:
                return
            yield ev

    return _iter(), queue


def _make_mock_client(watch_iter=None, **overrides) -> MagicMock:
    """建立 mock etcd client，含 watch() 回傳 async iterator。"""
    client = MagicMock()
    client.lease_grant = AsyncMock(return_value=12345)
    client.txn_put_if_not_exists = AsyncMock(return_value=True)
    client.lease_keepalive = AsyncMock()
    client.lease_revoke = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.close = AsyncMock()

    if watch_iter is None:
        # default: 永遠不發事件的 watch
        async def _empty_watch(key):
            # hang until cancelled
            await asyncio.Event().wait()
            yield  # unreachable, 但讓函式成 async generator

        client.watch = MagicMock(side_effect=lambda key: _empty_watch(key))
    else:
        client.watch = MagicMock(return_value=watch_iter)

    for k, v in overrides.items():
        setattr(client, k, v)
    return client


class TestWatchLeaderKey:
    @pytest.mark.asyncio
    async def test_external_delete_triggers_demotion_within_bounded_time(self):
        """外部刪除 election key 應在 < 500ms 內觸發 demotion。

        對照組：未實作 watch 時，需等 max_keepalive_failures × keepalive_interval ≈ 5s。
        """
        config = _make_config()
        on_demoted = AsyncMock()
        elector = LeaderElector(config=config, on_demoted=on_demoted)

        # Watch 在啟動後立即 yield 一個 DELETE 事件
        delete_event = FakeWatchEvent(
            event_type="DELETE",
            key=config.election_key,
        )
        watch_iter, watch_queue = _make_watch_queue([delete_event])

        mock_client = _make_mock_client(watch_iter=watch_iter)
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()

        # 等待 watch 偵測到 DELETE 並 demote — 預算 500ms
        # （未實作 watch 時，需等 max_keepalive_failures × keepalive_interval ≈ 5s
        #  → 此 500ms 預算內不可能 demote，可作為實作差距的客觀界線）
        deadline = asyncio.get_event_loop().time() + 0.5
        while asyncio.get_event_loop().time() < deadline:
            if on_demoted.await_count > 0:
                break
            await asyncio.sleep(0.01)

        # 應觀察到 demotion callback 被呼叫；state 可能因 campaign loop 立即重選
        # 又回到 LEADER（mock client 的 txn_put_if_not_exists 永遠成功），這是預期的
        # 「demote → re-campaign」行為，故只驗證 callback 而不卡 state。
        on_demoted.assert_awaited()

        await elector.stop()

    @pytest.mark.asyncio
    async def test_self_resign_does_not_trigger_demoted_callback_twice(self):
        """自身 resign 觸發的 DELETE 事件不應重複觸發 on_demoted。

        當 elector.resign() 主動撤銷 lease 時，etcd 會發 DELETE 事件，
        但這是預期內的 self-resign，不應再走 demotion 流程（避免 on_demoted 重複呼叫）。
        """
        config = _make_config()
        on_demoted = AsyncMock()
        elector = LeaderElector(config=config, on_demoted=on_demoted)

        # 一開始 watch 不發事件，由測試手動 push DELETE 模擬 etcd 對 self-resign 的回放
        watch_iter, watch_queue = _make_watch_queue([])

        mock_client = _make_mock_client(watch_iter=watch_iter)
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        await asyncio.sleep(0.05)
        assert elector.is_leader

        # 主動 resign — 這應該設置 self-resign 旗標
        await elector.resign()
        # 模擬 etcd 對自身 lease revoke 廣播 DELETE
        await watch_queue.put(FakeWatchEvent(event_type="DELETE", key=config.election_key))
        await asyncio.sleep(0.1)

        # on_demoted 不應該被呼叫（self-resign 不算 demoted）
        assert on_demoted.await_count == 0, (
            f"on_demoted should not be called on self-resign, got {on_demoted.await_count} calls"
        )

        await elector.stop()

    @pytest.mark.asyncio
    async def test_put_event_does_not_trigger_demotion(self):
        """PUT 事件（key 被更新）不該觸發 demotion，只有 DELETE 才該觸發。"""
        config = _make_config()
        on_demoted = AsyncMock()
        elector = LeaderElector(config=config, on_demoted=on_demoted)

        put_event = FakeWatchEvent(
            event_type="PUT",
            key=config.election_key,
            value="node-1@host",
        )
        watch_iter, _ = _make_watch_queue([put_event])

        mock_client = _make_mock_client(watch_iter=watch_iter)
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        await asyncio.sleep(0.2)

        assert elector.is_leader, "PUT event should not demote"
        assert on_demoted.await_count == 0

        await elector.stop()

    @pytest.mark.asyncio
    async def test_watch_exception_does_not_crash_elector(self):
        """watch() 拋例外不該讓 elector 整個崩潰，應重試或記錄並繼續。"""
        config = _make_config()
        elector = LeaderElector(config=config)

        call_count = {"n": 0}

        async def _flaky_watch(key):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ConnectionError("etcd disconnected")
            # 第二次正常等待（不發事件）
            await asyncio.Event().wait()
            yield  # unreachable

        mock_client = _make_mock_client()
        mock_client.watch = MagicMock(side_effect=lambda key: _flaky_watch(key))
        elector._create_etcd_client = MagicMock(return_value=mock_client)

        await elector.start()
        # 給 watch 機會重試
        await asyncio.sleep(0.3)

        # Elector 仍然是 leader（watch 失敗不該 demote）
        assert elector.is_leader
        # watch 至少被呼叫一次
        assert call_count["n"] >= 1

        await elector.stop()
