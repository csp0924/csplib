# =============== Monitor - Collector ===============
#
# 系統資料收集器
#
# 收集系統指標與模組健康狀態：
#   - SystemMetrics: 系統指標資料
#   - ModuleStatus: 模組狀態
#   - ModuleHealthSnapshot: 模組健康快照
#   - SystemMetricsCollector: 系統指標收集器
#   - ModuleHealthCollector: 模組健康收集器

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from csp_lib.core import HealthCheckable, HealthReport, HealthStatus, get_logger

if TYPE_CHECKING:
    from csp_lib.monitor.config import MonitorConfig

logger = get_logger(__name__)


@dataclass(frozen=True)
class InterfaceMetrics:
    """
    網路介面指標

    Attributes:
        name: 介面名稱
        bytes_sent: 已發送位元組
        bytes_recv: 已接收位元組
        send_rate: 發送速率（bytes/s）
        recv_rate: 接收速率（bytes/s）
    """

    name: str
    bytes_sent: int = 0
    bytes_recv: int = 0
    send_rate: float = 0.0
    recv_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        return {
            "name": self.name,
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "send_rate": round(self.send_rate, 1),
            "recv_rate": round(self.recv_rate, 1),
        }


@dataclass(frozen=True)
class SystemMetrics:
    """
    系統指標資料

    Attributes:
        cpu_percent: CPU 使用率（%）
        ram_percent: RAM 使用率（%）
        ram_used_mb: RAM 已使用量（MB）
        ram_total_mb: RAM 總量（MB）
        disk_usage: 磁碟使用率 {路徑: 百分比}
        net_bytes_sent: 網路已發送位元組
        net_bytes_recv: 網路已接收位元組
        net_send_rate: 網路發送速率（bytes/s）
        net_recv_rate: 網路接收速率（bytes/s）
    """

    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    disk_usage: dict[str, float] = field(default_factory=dict)
    net_bytes_sent: int = 0
    net_bytes_recv: int = 0
    net_send_rate: float = 0.0
    net_recv_rate: float = 0.0
    interface_metrics: dict[str, InterfaceMetrics] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        result: dict[str, Any] = {
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_percent": round(self.ram_percent, 1),
            "ram_used_mb": round(self.ram_used_mb, 1),
            "ram_total_mb": round(self.ram_total_mb, 1),
            "disk_usage": {k: round(v, 1) for k, v in self.disk_usage.items()},
            "net_bytes_sent": self.net_bytes_sent,
            "net_bytes_recv": self.net_bytes_recv,
            "net_send_rate": round(self.net_send_rate, 1),
            "net_recv_rate": round(self.net_recv_rate, 1),
        }
        if self.interface_metrics:
            result["interfaces"] = {name: m.to_dict() for name, m in self.interface_metrics.items()}
        return result


@dataclass(frozen=True)
class ModuleStatus:
    """
    模組狀態

    Attributes:
        name: 模組名稱
        status: 健康狀態
        message: 狀態訊息
        details: 附加資訊
    """

    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleHealthSnapshot:
    """
    模組健康快照

    Attributes:
        modules: 模組狀態列表
        overall_status: 整體健康狀態
    """

    modules: list[ModuleStatus]
    overall_status: HealthStatus

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        return {
            "overall_status": self.overall_status.value,
            "modules": {
                m.name: {
                    "status": m.status.value,
                    "message": m.message,
                    "details": m.details,
                }
                for m in self.modules
            },
        }


class SystemMetricsCollector:
    """
    系統指標收集器

    使用 psutil 收集 CPU、RAM、磁碟、網路指標。
    """

    def __init__(self, config: MonitorConfig) -> None:
        self._config = config
        self._last_net_bytes_sent: int = 0
        self._last_net_bytes_recv: int = 0
        self._last_net_time: float = 0.0
        self._last_iface_stats: dict[str, tuple[int, int]] = {}
        self._last_iface_time: float = 0.0

    def collect(self) -> SystemMetrics:
        """收集系統指標"""
        import psutil

        cpu_percent = 0.0
        if self._config.enable_cpu:
            cpu_percent = psutil.cpu_percent(interval=None)

        ram_percent = 0.0
        ram_used_mb = 0.0
        ram_total_mb = 0.0
        if self._config.enable_ram:
            mem = psutil.virtual_memory()
            ram_percent = mem.percent
            ram_used_mb = mem.used / (1024 * 1024)
            ram_total_mb = mem.total / (1024 * 1024)

        disk_usage: dict[str, float] = {}
        if self._config.enable_disk:
            for path in self._config.disk_paths:
                try:
                    usage = psutil.disk_usage(path)
                    disk_usage[path] = usage.percent
                except OSError:
                    logger.warning(f"無法讀取磁碟路徑: {path}")

        net_bytes_sent = 0
        net_bytes_recv = 0
        net_send_rate = 0.0
        net_recv_rate = 0.0
        if self._config.enable_network:
            net = psutil.net_io_counters()
            net_bytes_sent = net.bytes_sent
            net_bytes_recv = net.bytes_recv

            now = time.monotonic()
            if self._last_net_time > 0:
                elapsed = now - self._last_net_time
                if elapsed > 0:
                    net_send_rate = (net_bytes_sent - self._last_net_bytes_sent) / elapsed
                    net_recv_rate = (net_bytes_recv - self._last_net_bytes_recv) / elapsed

            self._last_net_bytes_sent = net_bytes_sent
            self._last_net_bytes_recv = net_bytes_recv
            self._last_net_time = now

        # Per-interface network metrics
        iface_metrics: dict[str, InterfaceMetrics] = {}
        if self._config.enable_network:
            try:
                pernic = psutil.net_io_counters(pernic=True)
                if pernic:
                    now_iface = time.monotonic()
                    allowed = self._config.network_interfaces

                    for iface_name, counters in pernic.items():
                        if allowed is not None and iface_name not in allowed:
                            continue

                        iface_send_rate = 0.0
                        iface_recv_rate = 0.0
                        if self._last_iface_time > 0 and iface_name in self._last_iface_stats:
                            elapsed = now_iface - self._last_iface_time
                            if elapsed > 0:
                                prev_sent, prev_recv = self._last_iface_stats[iface_name]
                                iface_send_rate = (counters.bytes_sent - prev_sent) / elapsed
                                iface_recv_rate = (counters.bytes_recv - prev_recv) / elapsed

                        self._last_iface_stats[iface_name] = (counters.bytes_sent, counters.bytes_recv)
                        iface_metrics[iface_name] = InterfaceMetrics(
                            name=iface_name,
                            bytes_sent=counters.bytes_sent,
                            bytes_recv=counters.bytes_recv,
                            send_rate=iface_send_rate,
                            recv_rate=iface_recv_rate,
                        )

                    self._last_iface_time = now_iface
            except Exception:
                logger.warning("無法收集網路介面指標", exc_info=True)

        return SystemMetrics(
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            ram_used_mb=ram_used_mb,
            ram_total_mb=ram_total_mb,
            disk_usage=disk_usage,
            net_bytes_sent=net_bytes_sent,
            net_bytes_recv=net_bytes_recv,
            net_send_rate=net_send_rate,
            net_recv_rate=net_recv_rate,
            interface_metrics=iface_metrics,
        )


class ModuleHealthCollector:
    """
    模組健康收集器

    註冊 HealthCheckable 模組與自訂檢查函式，
    收集彙總模組健康狀態。
    """

    def __init__(self) -> None:
        self._modules: dict[str, HealthCheckable] = {}
        self._checks: dict[str, Callable[[], HealthReport]] = {}

    def register_module(self, name: str, module: HealthCheckable) -> None:
        """註冊 HealthCheckable 模組"""
        self._modules[name] = module

    def register_check(self, name: str, check_fn: Callable[[], HealthReport]) -> None:
        """註冊自訂健康檢查函式"""
        self._checks[name] = check_fn

    def collect(self) -> ModuleHealthSnapshot:
        """收集所有模組健康狀態"""
        statuses: list[ModuleStatus] = []

        for name, module in self._modules.items():
            try:
                report = module.health()
                statuses.append(
                    ModuleStatus(
                        name=name,
                        status=report.status,
                        message=report.message,
                        details=report.details,
                    )
                )
            except Exception as e:
                statuses.append(
                    ModuleStatus(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"健康檢查失敗: {e}",
                    )
                )

        for name, check_fn in self._checks.items():
            try:
                report = check_fn()
                statuses.append(
                    ModuleStatus(
                        name=name,
                        status=report.status,
                        message=report.message,
                        details=report.details,
                    )
                )
            except Exception as e:
                statuses.append(
                    ModuleStatus(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"健康檢查失敗: {e}",
                    )
                )

        overall = self._compute_overall(statuses)
        return ModuleHealthSnapshot(modules=statuses, overall_status=overall)

    @staticmethod
    def _compute_overall(statuses: list[ModuleStatus]) -> HealthStatus:
        """計算整體健康狀態"""
        if not statuses:
            return HealthStatus.HEALTHY

        if any(s.status == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s.status == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY


__all__ = [
    "InterfaceMetrics",
    "ModuleHealthCollector",
    "ModuleHealthSnapshot",
    "ModuleStatus",
    "SystemMetrics",
    "SystemMetricsCollector",
]
