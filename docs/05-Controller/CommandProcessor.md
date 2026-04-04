---
tags:
  - type/protocol
  - layer/controller
  - status/complete
source: csp_lib/controller/core/processor.py
updated: 2026-04-04
version: ">=0.5.0"
---

# CommandProcessor

Post-Protection 命令處理器 Protocol，定義在 [[ProtectionGuard]] 和 CommandRouter 之間的處理管線。

> [!info] v0.5.0 新增

> [!info] 回到 [[_MOC Controller]]

## 概述

`CommandProcessor` 是 `@runtime_checkable Protocol`，定義了 post-protection 階段的命令處理介面。典型用途包括功率補償、命令日誌、審計追蹤等。

### 執行流程

```
Strategy.execute()
  → ProtectionGuard.apply()
  → [CommandProcessor 1] → [CommandProcessor 2] → ...
  → CommandRouter.route()
```

## Protocol 定義

```python
@runtime_checkable
class CommandProcessor(Protocol):
    async def process(self, command: Command, context: StrategyContext) -> Command:
        """
        處理命令

        Args:
            command: 經保護鏈處理後的命令
            context: 當前策略上下文

        Returns:
            處理後的命令
        """
        ...
```

## 介面語義

| 項目 | 說明 |
|------|------|
| 輸入 | 經保護鏈處理後的 [[Command]] 和當前 [[StrategyContext]] |
| 輸出 | 處理後的 [[Command]]（可修改 `p_target` / `q_target`） |
| 例外處理 | 拋出例外時，SystemController 會 log 並跳過此 processor，繼續後續處理 |

## Pipeline 串接

多個 `CommandProcessor` 按順序串接，每個 processor 的輸出作為下一個的輸入：

```python
from csp_lib.integration import SystemControllerConfig

config = SystemControllerConfig(
    post_protection_processors=[
        compensator,    # 功率補償
        logger_proc,    # 命令日誌
        audit_proc,     # 審計追蹤
    ],
)
```

## Quick Example

```python
from csp_lib.controller.core import Command, StrategyContext

class MyCompensator:
    """自訂命令處理器"""

    async def process(self, command: Command, context: StrategyContext) -> Command:
        compensated_p = self._compensate(command.p_target)
        return command.with_p(compensated_p)

    def _compensate(self, p: float) -> float:
        # 自訂補償邏輯
        return p * 1.02

# 註冊至 SystemControllerConfig
from csp_lib.integration import SystemControllerConfig

config = SystemControllerConfig(
    post_protection_processors=[MyCompensator()],
)
```

## 內建實作

- [[PowerCompensator]] — FF + I 閉環功率補償器

## 相關連結

- [[ProtectionGuard]] — 保護鏈（CommandProcessor 位於其後）
- [[PowerCompensator]] — 內建的功率補償實作
- [[Command]] — 處理的命令物件
- [[StrategyContext]] — 策略上下文
