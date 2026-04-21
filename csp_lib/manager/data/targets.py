# =============== Manager Data - Upload Targets ===============
#
# 資料上傳目標（fan-out target）定義
#
# 提供：
#   - WritePolicy: 寫入策略列舉（ALWAYS / ON_CHANGE / INTERVAL）
#   - UploadTarget: 上傳目標 frozen dataclass（collection + transform + policy）
#   - TransformFn / TransformResult: transform callable 型別別名
#
# 設計目的：
#   讓同一設備的讀取資料可以 fan-out 到多個 collection，
#   每個 target 可帶獨立的 transform（將 raw values 轉換成目標 schema）
#   與 WritePolicy（是否每次都寫、僅變動時寫、或依固定間隔寫）。

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

# ================ 型別別名 ================

TransformResult = dict[str, Any] | list[dict[str, Any]] | None
"""Transform callable 的回傳型別。

- ``dict``：單一文件（會被正規化為 ``[dict]``）
- ``list[dict]``：多文件（fan-out 成多筆記錄）
- ``None``：跳過此次寫入（例如資料未就緒）
"""

TransformFn = Callable[[dict[str, Any]], TransformResult]
"""Transform callable 型別。

輸入 raw values（``ReadCompletePayload.values``），
輸出目標 collection 的文件（單筆、多筆、或 None 代表跳過）。
"""


# ================ WritePolicy ================


class WritePolicy(str, Enum):
    """寫入策略。

    控制 ``UploadTarget`` 何時將 transform 結果寫入 collection。

    Values:
        ALWAYS: 每次 read_complete 事件都寫入（高頻寫）。
        ON_CHANGE: 僅當 transform 結果與上次不同時才寫入（去重）。
        INTERVAL: 依固定時間間隔寫入（目前尚未實作，設定會觸發 NotImplementedError）。
    """

    ALWAYS = "always"
    ON_CHANGE = "on_change"
    INTERVAL = "interval"


# ================ UploadTarget ================


@dataclass(frozen=True, slots=True)
class UploadTarget:
    """上傳目標定義。

    一個 ``UploadTarget`` 描述「把 device 的 raw values 透過 transform
    送到某個 collection」的完整規則。多個 target 可以綁定到同一設備
    以達成 fan-out（同一次讀取寫到多個 collection）。

    Attributes:
        collection: 目標 collection 名稱。
        transform: 將 raw values 轉為目標文件（或文件列表）的 callable。
        policy: 寫入策略（``WritePolicy.ALWAYS`` / ``ON_CHANGE`` / ``INTERVAL``）。

    Example:
        ```python
        def summary_transform(values: dict) -> dict:
            return {"avg": sum(values.values()) / len(values)}

        def detail_transform(values: dict) -> list[dict]:
            return [{"key": k, "value": v} for k, v in values.items()]

        targets = [
            UploadTarget(
                collection="summary_coll",
                transform=summary_transform,
                policy=WritePolicy.ON_CHANGE,
            ),
            UploadTarget(
                collection="detail_coll",
                transform=detail_transform,
                policy=WritePolicy.ALWAYS,
            ),
        ]
        ```
    """

    collection: str
    transform: TransformFn
    policy: WritePolicy = WritePolicy.ALWAYS


__all__ = [
    "TransformFn",
    "TransformResult",
    "UploadTarget",
    "WritePolicy",
]
