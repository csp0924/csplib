# =============== Manager Tests - Protocol Conformance ===============
#
# 驗證所有 In-Memory 實作符合對應的 Protocol
#
# 使用 runtime_checkable Protocol isinstance 測試
# 確保實作不遺漏任何必要方法

from __future__ import annotations

import pytest

from csp_lib.manager.alarm.in_memory import InMemoryAlarmRepository
from csp_lib.manager.alarm.repository import AlarmRepository
from csp_lib.manager.base import AsyncRepository, BatchUploader
from csp_lib.manager.command.in_memory import InMemoryCommandRepository
from csp_lib.manager.command.repository import CommandRepository
from csp_lib.manager.in_memory_uploader import InMemoryBatchUploader, NullBatchUploader
from csp_lib.manager.schedule.in_memory import InMemoryScheduleRepository
from csp_lib.manager.schedule.repository import ScheduleRepository


class TestBatchUploaderConformance:
    """BatchUploader Protocol conformance"""

    @pytest.mark.parametrize("cls", [NullBatchUploader, InMemoryBatchUploader])
    def test_isinstance_check(self, cls):
        """實例應通過 isinstance(obj, BatchUploader)"""
        instance = cls()
        assert isinstance(instance, BatchUploader)

    @pytest.mark.parametrize("cls", [NullBatchUploader, InMemoryBatchUploader])
    def test_has_register_collection(self, cls):
        """必須有 register_collection 方法"""
        instance = cls()
        assert hasattr(instance, "register_collection")
        assert callable(instance.register_collection)

    @pytest.mark.parametrize("cls", [NullBatchUploader, InMemoryBatchUploader])
    def test_has_enqueue(self, cls):
        """必須有 enqueue 方法"""
        instance = cls()
        assert hasattr(instance, "enqueue")
        assert callable(instance.enqueue)


class TestAsyncRepositoryConformance:
    """AsyncRepository Protocol conformance"""

    @pytest.mark.parametrize(
        "cls",
        [InMemoryAlarmRepository, InMemoryCommandRepository, InMemoryScheduleRepository],
    )
    def test_isinstance_check(self, cls):
        """所有 In-Memory Repository 應通過 isinstance(obj, AsyncRepository)"""
        instance = cls()
        assert isinstance(instance, AsyncRepository)


class TestAlarmRepositoryConformance:
    """AlarmRepository Protocol conformance"""

    def test_isinstance_check(self):
        """InMemoryAlarmRepository 應通過 isinstance(obj, AlarmRepository)"""
        instance = InMemoryAlarmRepository()
        assert isinstance(instance, AlarmRepository)

    @pytest.mark.parametrize(
        "method", ["health_check", "upsert", "resolve", "get_active_alarms", "get_active_by_device"]
    )
    def test_has_required_methods(self, method: str):
        """必須有 Protocol 定義的所有方法"""
        instance = InMemoryAlarmRepository()
        assert hasattr(instance, method)
        assert callable(getattr(instance, method))


class TestCommandRepositoryConformance:
    """CommandRepository Protocol conformance"""

    def test_isinstance_check(self):
        """InMemoryCommandRepository 應通過 isinstance(obj, CommandRepository)"""
        instance = InMemoryCommandRepository()
        assert isinstance(instance, CommandRepository)

    @pytest.mark.parametrize("method", ["health_check", "create", "update_status", "get", "list_by_device"])
    def test_has_required_methods(self, method: str):
        """必須有 Protocol 定義的所有方法"""
        instance = InMemoryCommandRepository()
        assert hasattr(instance, method)
        assert callable(getattr(instance, method))


class TestScheduleRepositoryConformance:
    """ScheduleRepository Protocol conformance"""

    def test_isinstance_check(self):
        """InMemoryScheduleRepository 應通過 isinstance(obj, ScheduleRepository)"""
        instance = InMemoryScheduleRepository()
        assert isinstance(instance, ScheduleRepository)

    @pytest.mark.parametrize("method", ["health_check", "find_active_rules", "get_all_enabled", "upsert"])
    def test_has_required_methods(self, method: str):
        """必須有 Protocol 定義的所有方法"""
        instance = InMemoryScheduleRepository()
        assert hasattr(instance, method)
        assert callable(getattr(instance, method))
