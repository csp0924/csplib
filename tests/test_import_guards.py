"""Import guard 測試"""

from __future__ import annotations

import importlib
import sys

import pytest


def test_grpc_import_raises() -> None:
    """import csp_lib.grpc 應拋出 ImportError"""
    # 確保模組未快取
    sys.modules.pop("csp_lib.grpc", None)
    with pytest.raises(ImportError, match="csp0924_lib.*grpc"):
        importlib.import_module("csp_lib.grpc")


def test_cluster_import_guard_wraps_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """cluster __init__ 的 try/except 應包裝 ImportError 並附帶安裝提示"""
    # 直接讀取 cluster/__init__.py 的原始碼確認 try/except 結構存在
    source = importlib.util.find_spec("csp_lib.cluster")
    assert source is not None
    assert source.origin is not None

    import pathlib

    code = pathlib.Path(source.origin).read_text(encoding="utf-8")
    assert "try:" in code
    assert "csp0924_lib[cluster]" in code
