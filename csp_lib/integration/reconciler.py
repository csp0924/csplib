# =============== Integration - Reconciler Protocol (re-export shim) ===============
#
# v0.9.x 之前 Reconciler Protocol 位於此處；Wave 2c-F（csp_lib 0.10.x）下移至
# ``csp_lib.core.reconciler`` 以便 manager 層（如 ScheduleService）實作
# 而不產生「manager → integration」反向依賴。
#
# 此檔維持原有 import path 的向後相容：``from csp_lib.integration.reconciler
# import Reconciler, ReconcilerMixin, ReconcilerStatus`` 仍然有效。

from __future__ import annotations

from csp_lib.core.reconciler import Reconciler, ReconcilerMixin, ReconcilerStatus

__all__ = [
    "Reconciler",
    "ReconcilerMixin",
    "ReconcilerStatus",
]
