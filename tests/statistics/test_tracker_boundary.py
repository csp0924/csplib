# =============== Statistics Tests - Tracker boundary truncation ===============
#
# 針對 IntervalAccumulator._finalize 的 boundary truncation bug 撰寫的回歸測試。
#
# Bug 描述：
#   舊版 _finalize 直接以 `_kwh_accumulated` 結算當下 interval，未處理 boundary 前
#   最後一個 sample 到 boundary 之間的尾段；CUMULATIVE 也只取最後 sample 而非
#   boundary 對應值。emergent 後果是 constant 信號每 interval 都低估，低估比例
#   ≈ sample_period / interval_size。
#
# 修復策略（boundary-aligned linear interpolation）：
#   feed() 在偵測到 boundary cross（timestamp >= boundary）時，使用剛抵達的
#   sample 與 prev sample 做 *內插*，估出 boundary 瞬間的 value：
#       v_b = prev_value + (value - prev_value) * (boundary - prev_ts) / (ts - prev_ts)
#   - INSTANTANEOUS: 補上 trapezoid 尾段 (prev_value + v_b)/2 * (boundary - prev_ts).hours
#   - CUMULATIVE: kwh = v_b - first_value
#   下一個 interval 以 (v_b, boundary) 為合成種子 sample，再 accumulate 真實抵達的
#   sample → 跨 interval 連續，無 leakage。
#
# 對 constant 信號完全精確；對 ramp 信號是兩個內插端點的二階近似。

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from csp_lib.statistics.config import DeviceMeterType
from csp_lib.statistics.tracker import IntervalAccumulator, IntervalRecord


def _run_constant_power(
    meter_type: DeviceMeterType,
    sample_period_seconds: float,
    duration_minutes: int,
    power_kw: float = 10.0,
    interval_minutes: int = 15,
) -> list[IntervalRecord]:
    """共用：以恆定功率 power_kw 餵入 acc，回傳所有完成的 IntervalRecord。

    sample 從 12:00:00（恰好對齊 15min boundary）起，間隔 sample_period_seconds 餵入，
    共 duration_minutes 分鐘。CUMULATIVE 餵入累計值，INSTANTANEOUS 餵入恆定功率值。
    """
    base = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
    acc = IntervalAccumulator(
        device_id="DEV1",
        interval_minutes=interval_minutes,
        meter_type=meter_type,
    )
    records: list[IntervalRecord] = []
    total_seconds = duration_minutes * 60
    n_samples = int(total_seconds / sample_period_seconds) + 1
    for i in range(n_samples):
        t = i * sample_period_seconds
        ts = base + timedelta(seconds=t)
        if meter_type == DeviceMeterType.CUMULATIVE:
            value = power_kw * (t / 3600.0)
        else:
            value = power_kw
        rec = acc.feed(value, ts)
        if rec is not None:
            records.append(rec)
    return records


class TestBoundaryNoTruncation:
    """boundary truncation 修復後：constant power 每 interval 應達理論值。"""

    def test_instantaneous_constant_power_matches_theoretical(self) -> None:
        """INSTANTANEOUS：10 kW 定值、60 s 取樣、15 min interval → 每 record 2.5 kWh。

        修復前舊版回 2.3333 kWh（低估 6.67% = 1/15 = sample_period/interval）。
        """
        records = _run_constant_power(
            meter_type=DeviceMeterType.INSTANTANEOUS,
            sample_period_seconds=60.0,
            duration_minutes=60,
        )
        # 60 分鐘 / 15 分鐘 = 4 個完整 interval，但首 interval 起點若恰好對齊，
        # 仍能完整結算；最後一個 interval 未跨越 boundary 不會 emit。
        assert len(records) >= 3
        for r in records:
            assert r.kwh == pytest.approx(2.5, abs=1e-3), (
                f"interval {r.period_start}~{r.period_end} kwh={r.kwh} (expected 2.5)"
            )

    def test_instantaneous_180s_sampling_under_report_eliminated(self) -> None:
        """INSTANTANEOUS：180 s 取樣低估 20% 的舊 bug 應消失。

        修復前每 record 約 2.0 kWh（低估 20% = 180/900）；修復後 ≈ 2.5 kWh。
        """
        records = _run_constant_power(
            meter_type=DeviceMeterType.INSTANTANEOUS,
            sample_period_seconds=180.0,
            duration_minutes=60,
        )
        assert len(records) >= 3
        for r in records:
            assert r.kwh == pytest.approx(2.5, abs=1e-3), (
                f"interval {r.period_start}~{r.period_end} kwh={r.kwh} (expected 2.5, shortfall must be < 0.04%)"
            )

    def test_instantaneous_5s_sampling_high_accuracy(self) -> None:
        """INSTANTANEOUS：5 s 取樣（near-continuous）每 record 也應 ≈ 2.5 kWh。"""
        records = _run_constant_power(
            meter_type=DeviceMeterType.INSTANTANEOUS,
            sample_period_seconds=5.0,
            duration_minutes=60,
        )
        assert len(records) >= 3
        for r in records:
            assert r.kwh == pytest.approx(2.5, abs=1e-4)

    def test_cumulative_constant_power_matches_theoretical(self) -> None:
        """CUMULATIVE：10 kW 定值、60 s 取樣 → 每 record 2.5 kWh。

        修復前舊版回 2.333 kWh（last - first 漏 boundary 段）。
        """
        records = _run_constant_power(
            meter_type=DeviceMeterType.CUMULATIVE,
            sample_period_seconds=60.0,
            duration_minutes=60,
        )
        assert len(records) >= 3
        for r in records:
            assert r.kwh == pytest.approx(2.5, abs=1e-3), (
                f"interval {r.period_start}~{r.period_end} kwh={r.kwh} (expected 2.5)"
            )

    def test_cumulative_180s_sampling_no_under_report(self) -> None:
        """CUMULATIVE：180 s 取樣修復後每 record ≈ 2.5 kWh。"""
        records = _run_constant_power(
            meter_type=DeviceMeterType.CUMULATIVE,
            sample_period_seconds=180.0,
            duration_minutes=60,
        )
        assert len(records) >= 3
        for r in records:
            assert r.kwh == pytest.approx(2.5, abs=1e-3)

    def test_cumulative_continuous_across_intervals(self) -> None:
        """CUMULATIVE 模式跨 interval 連續：總和應接近 INSTANTANEOUS 結果。

        Bug 修復後 CUMULATIVE 上一個 interval 結算用 boundary 內插值，下一個 interval
        以該值起算 → 跨 interval 無 leakage，總 kWh 應與 INSTANTANEOUS 一致。
        """
        cum_records = _run_constant_power(
            meter_type=DeviceMeterType.CUMULATIVE,
            sample_period_seconds=60.0,
            duration_minutes=60,
        )
        inst_records = _run_constant_power(
            meter_type=DeviceMeterType.INSTANTANEOUS,
            sample_period_seconds=60.0,
            duration_minutes=60,
        )
        cum_total = sum(r.kwh for r in cum_records)
        inst_total = sum(r.kwh for r in inst_records)
        assert cum_total == pytest.approx(inst_total, abs=1e-3)


class TestFirstIntervalPartial:
    """首 sample 不在 period_start 時，首個 interval 是部分樣本是 by-design。

    說明：我們無從得知 period_start 那一刻的真實 value，不做 backfill。第一個 interval
    必然只覆蓋 [first_sample_ts, boundary]；後續 interval 才完整覆蓋 [boundary, next_boundary]。
    """

    def test_first_interval_starts_at_first_sample_caveat(self) -> None:
        """首 sample 落在 interval 中段時，首個 record 涵蓋 first_sample → boundary。"""
        base = datetime(2026, 5, 13, 12, 7, 0, tzinfo=timezone.utc)
        acc = IntervalAccumulator(
            device_id="DEV1",
            interval_minutes=15,
            meter_type=DeviceMeterType.INSTANTANEOUS,
        )
        # 12:07 起，每 60 s 一筆 10 kW，到 12:16 跨越 12:15 boundary
        records: list[IntervalRecord] = []
        for i in range(11):
            ts = base + timedelta(seconds=i * 60)
            r = acc.feed(10.0, ts)
            if r is not None:
                records.append(r)
        assert len(records) == 1
        r = records[0]
        # 首個 interval [12:00, 12:15]，但只從 12:07 開始；應約 = 10 * 8/60 ≈ 1.333 kWh
        assert r.period_start == datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        assert r.period_end == datetime(2026, 5, 13, 12, 15, 0, tzinfo=timezone.utc)
        assert r.kwh == pytest.approx(10.0 * 8 / 60.0, abs=1e-3)

    def test_subsequent_intervals_after_partial_first_are_complete(self) -> None:
        """首個 partial interval 後，後續 interval 應回到完整 2.5 kWh。"""
        base = datetime(2026, 5, 13, 12, 7, 0, tzinfo=timezone.utc)
        acc = IntervalAccumulator(
            device_id="DEV1",
            interval_minutes=15,
            meter_type=DeviceMeterType.INSTANTANEOUS,
        )
        records: list[IntervalRecord] = []
        # 12:07 → 12:60 (53 分鐘 → 53 筆 + 1 邊界外，共 54 筆)
        for i in range(54):
            ts = base + timedelta(seconds=i * 60)
            r = acc.feed(10.0, ts)
            if r is not None:
                records.append(r)
        # 應產生第一個 partial + 後續完整 records
        assert len(records) >= 3
        # 第二個 onwards 應為完整 2.5
        for r in records[1:]:
            assert r.kwh == pytest.approx(2.5, abs=1e-3)


class TestMultiIntervalSkip:
    """讀數跨越 >1 個 interval boundary 時，gap 能量不得灌進新 interval。

    Bug 描述（PR #146 Copilot review）：
      舊版 feed() 在偵測到 timestamp >= boundary 時，只 finalize 第一個跨界的 interval，
      之後把 `_period_start` 直接跳到 floor(timestamp)（可能跨好幾個 interval），但
      seed 卻是用第一個 boundary 的內插值（舊 boundary）。接著 `_accumulate(value, ts)`
      會以 (prev_value=v_b@舊 boundary, prev_ts=舊 boundary) 為起點對 timestamp 算
      trapezoid，等於把整個 gap（橫跨數個 interval）的能量塞給「最後落點的當前 interval」。

      Emergent 後果：若取樣斷線（例如 Modbus timeout 半小時），恢復後第一筆 sample
      所屬 interval 的 kWh 會被嚴重灌水；中間被跳過的 interval 則完全沒有 record。

    修復策略：
      偵測到多 interval 跨越時，以 `_period_start = floor(timestamp)` 對應的時刻
      （新 interval 的 period_start）做內插得到 v@period_start，然後以該值為新
      interval 的合成 seed，而不是用舊 boundary 的內插值。如此新 interval 從
      period_start 起算，accumulate 真實 sample 時的 trapezoid 僅覆蓋
      [period_start, timestamp]，不會把 gap 灌進來。中間被跳過的 interval 不
      emit record（we don't have enough data to attribute partial intervals）。
    """

    def test_instantaneous_gap_does_not_inflate_current_interval(self) -> None:
        """INSTANTANEOUS：12:00 餵 10 kW，沉默到 12:46 才再餵 10 kW；新 interval
        [12:45, 13:00] 在後續完成時應為 ≈ 2.5 kWh，而非 7.5 kWh（gap 灌水）。

        Bug 重現：
          - 舊版會把 12:15→12:46 的 trapezoid (≈ 5.167 kWh) 塞進 [12:45, 13:00]，
            之後 13:01 再餵一筆完成 interval 時得 7.5 kWh。
          - 修復後新 interval 從 12:45 (內插值 10 kW) seed，13:01 完成時為 2.5 kWh。
        """
        base = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        acc = IntervalAccumulator(
            device_id="DEV1",
            interval_minutes=15,
            meter_type=DeviceMeterType.INSTANTANEOUS,
        )
        # 12:00 起首筆 sample
        r0 = acc.feed(10.0, base)
        assert r0 is None
        # 沉默 46 分鐘，跨越 12:15 / 12:30 / 12:45 三個 boundary
        gap_ts = base + timedelta(minutes=46)
        r1 = acc.feed(10.0, gap_ts)
        # 第一個 boundary [12:00, 12:15] 仍應 emit，且 ≈ 2.5 kWh
        assert r1 is not None
        assert r1.period_start == base
        assert r1.period_end == base + timedelta(minutes=15)
        assert r1.kwh == pytest.approx(2.5, abs=1e-3)
        # 接著 13:01 完成 [12:45, 13:00]：應為完整 2.5 kWh（沒被 gap 灌水）
        r2 = acc.feed(10.0, base + timedelta(minutes=61))
        assert r2 is not None
        assert r2.period_start == base + timedelta(minutes=45)
        assert r2.period_end == base + timedelta(minutes=60)
        assert r2.kwh == pytest.approx(2.5, abs=1e-3), (
            f"gap 能量被灌進 [12:45, 13:00]，kwh={r2.kwh} (expected ≈ 2.5, bug 表現為 ≈ 7.5)"
        )

    def test_cumulative_gap_does_not_inflate_current_interval(self) -> None:
        """CUMULATIVE：用 10 kW 恆功率對應的累積值跨多 interval 沉默，
        新 interval 結算應為 ≈ 2.5 kWh，不含 gap 段。

        舊 bug：CUMULATIVE 在新 interval seed `_first_value = v_b@舊 boundary`，
        finalize 時 kwh = v_b@新 boundary - v_b@舊 boundary，等於把整個 gap 算進去。
        """
        base = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        acc = IntervalAccumulator(
            device_id="DEV1",
            interval_minutes=15,
            meter_type=DeviceMeterType.CUMULATIVE,
        )

        # CUMULATIVE：value = 10 kW * elapsed_hours
        def cum_value(t_min: float) -> float:
            return 10.0 * (t_min / 60.0)

        # 12:00 起，cum = 0
        r0 = acc.feed(cum_value(0), base)
        assert r0 is None
        # 沉默到 12:46，cum = 10 * 46/60 ≈ 7.6667
        r1 = acc.feed(cum_value(46), base + timedelta(minutes=46))
        assert r1 is not None
        # 第一個 interval [12:00, 12:15]：v_b@12:15 = 10*15/60 = 2.5 → kwh = 2.5 - 0 = 2.5
        assert r1.kwh == pytest.approx(2.5, abs=1e-3)
        # 13:01 完成 [12:45, 13:00]：應為 2.5 kWh（不是 7.5）
        r2 = acc.feed(cum_value(61), base + timedelta(minutes=61))
        assert r2 is not None
        assert r2.period_start == base + timedelta(minutes=45)
        assert r2.kwh == pytest.approx(2.5, abs=1e-3), (
            f"CUMULATIVE 新 interval 把 gap 段算進去，kwh={r2.kwh} (expected ≈ 2.5)"
        )

    def test_instantaneous_period_start_after_multi_skip_is_floored(self) -> None:
        """多 interval 跨越後，新 interval 的 period_start 必為 floor(timestamp)。"""
        base = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        acc = IntervalAccumulator(
            device_id="DEV1",
            interval_minutes=15,
            meter_type=DeviceMeterType.INSTANTANEOUS,
        )
        acc.feed(10.0, base)
        # 跨越 12:15 / 12:30 / 12:45，停在 12:46
        acc.feed(10.0, base + timedelta(minutes=46))
        # period_start 應跳到 12:45（floor(12:46) = 12:45）
        assert acc.period_start == base + timedelta(minutes=45)
