# =============== Strategy 參數解析器 ===============
#
# ParamResolver：整合 RuntimeParameters (執行期可變) 與 frozen config (啟動期不可變)
# 的參數讀取管道，供各策略的 execute() 內部使用。
#
# 解析規則：
#   1. 若 field 出現在 param_keys 映射中，且 params.get(mapped_key) 非 None，
#      則回傳 runtime 值（若有 scale 則套用倍率）
#   2. 否則 fallback 到 getattr(config, field)（若有 scale 則套用倍率）
#
# 此 helper 僅供 strategies 內部使用，不對外 export。

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from csp_lib.core.runtime_params import RuntimeParameters


class ParamResolver:
    """解析 strategy 執行期參數：params (runtime) 優先，缺失 fallback 到 config。

    設計原則：
        - ``param_keys`` 明列的欄位允許從 ``params`` 動態讀取；
          未列於 ``param_keys`` 的欄位一律 fallback 到 ``config`` 屬性。
        - ``params.get(key)`` 回 ``None`` 視為該欄位未被 EMS 覆寫，同樣 fallback。
        - ``scale`` 提供每欄位獨立倍率，套用於 ``resolve()`` 的最終結果
          （不論值來自 params 或 config）。

    Args:
        params: RuntimeParameters 實例，或 None（表示純 config 模式）。
        param_keys: 欄位名到 runtime key 的映射。必須與 ``params`` 同為 None 或同為非 None。
        config: 提供 fallback 值的 frozen dataclass 實例。
        scale: 每欄位的倍率，預設為 None（不做縮放）。

    Raises:
        ValueError: 當 ``params`` 與 ``param_keys`` 一個為 None 一個非 None 時。

    Example:
        >>> cfg = DroopConfig(droop=0.05)
        >>> params = RuntimeParameters(droop_pct=4.0)
        >>> resolver = ParamResolver(
        ...     params=params,
        ...     param_keys={"droop": "droop_pct"},
        ...     config=cfg,
        ...     scale={"droop": 0.01},  # runtime 值是百分比，需乘 0.01
        ... )
        >>> resolver.resolve("droop")  # 回傳 4.0 * 0.01 = 0.04
        0.04
    """

    __slots__ = ("_params", "_param_keys", "_config", "_scale")

    def __init__(
        self,
        *,
        params: RuntimeParameters | None,
        param_keys: Mapping[str, str] | None,
        config: object,
        scale: Mapping[str, float] | None = None,
    ) -> None:
        # 驗證：params 與 param_keys 必須同時為 None 或同時非 None
        if (params is None) != (param_keys is None):
            raise ValueError("params and param_keys must both be provided or both be None")

        self._params = params
        self._param_keys = dict(param_keys) if param_keys is not None else None
        self._config = config
        self._scale = dict(scale) if scale is not None else None

    @property
    def has_runtime(self) -> bool:
        """是否具備 runtime 參數來源（params 與 param_keys 均提供）。"""
        return self._params is not None

    def with_config(self, config: object) -> ParamResolver:
        """建立一份 config 已替換的新 resolver，保留原有的 params / param_keys / scale。

        用於 strategy.update_config() 時重建 resolver。

        Args:
            config: 新的 frozen config 實例。

        Returns:
            新的 ParamResolver 實例。
        """
        return ParamResolver(
            params=self._params,
            param_keys=self._param_keys,
            config=config,
            scale=self._scale,
        )

    def resolve(self, field: str) -> Any:
        """解析欄位值：params → config，再套 scale（若有）。

        Args:
            field: 欲解析的欄位名（對應 config 的屬性名）。

        Returns:
            欄位值：
                * 若 ``field`` 在 ``param_keys`` 且 ``params.get(mapped_key)`` 非 ``None``，
                  回 runtime 值（已套 scale）
                * 否則回 ``getattr(config, field)``（已套 scale）
        """
        value: Any = None
        if self._params is not None and self._param_keys is not None:
            mapped_key = self._param_keys.get(field)
            if mapped_key is not None:
                runtime_value = self._params.get(mapped_key)
                if runtime_value is not None:
                    value = runtime_value

        if value is None:
            value = getattr(self._config, field)

        # 套用 scale（僅對數值型；若欄位不在 scale 中則原樣回傳）
        if self._scale is not None:
            factor = self._scale.get(field)
            if factor is not None:
                value = value * factor

        return value

    def resolve_optional(self, key: str | None, default: Any = None) -> Any:
        """解析 runtime-only 參數，不 fallback 到 config。

        用於 ``enabled_key`` / ``schedule_p_key`` 等不存在於 config 的旗標。

        Args:
            key: runtime key 名稱。若為 ``None`` 或 ``params`` 為 ``None``，回 ``default``。
            default: 缺失時的預設值。

        Returns:
            ``params.get(key, default)``，或 ``default``（若 key 或 params 為 None）。
        """
        if key is None or self._params is None:
            return default
        value = self._params.get(key)
        return default if value is None else value


__all__ = ["ParamResolver"]
