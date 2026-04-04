---
tags:
  - type/moc
  - layer/modbus
  - status/complete
source: csp_lib/modbus/
created: 2026-02-17
updated: 2026-04-04
version: 0.6.0
---

# _MOC Modbus

## Modbus 通訊協定層 (`csp_lib.modbus`)

> [!info] 安裝
> 需安裝：`pip install csp0924_lib[modbus]`

提供 Modbus TCP/RTU 通訊，包含資料型別、編解碼、非同步客戶端。此模組為整個設備通訊架構的最底層，所有設備讀寫操作最終都透過此模組完成。

---

## 頁面索引

| 頁面 | 說明 |
|------|------|
| [[Data Types]] | Modbus 資料型別定義（Int16、Float32、ModbusString 等） |
| [[ModbusCodec]] | 高階編解碼器，封裝 ByteOrder 與 RegisterOrder |
| [[Enums]] | 列舉常數（ByteOrder、RegisterOrder、Parity、FunctionCode） |
| [[Configuration]] | 連線設定類別（ModbusTcpConfig、ModbusRtuConfig） |
| [[Clients]] | 非同步客戶端（TCP、RTU、共享 TCP） |
| [[Exceptions]] | 例外類別階層 |

---

## 模組架構

```
csp_lib.modbus
├── types/          # 資料型別 (Int16, Float32, ModbusString...)
│   ├── base.py     # ModbusDataType 抽象基底類別
│   ├── numeric.py  # 固定長度數值型別
│   ├── dynamic.py  # 動態長度整數型別
│   └── string.py   # 字串型別
├── clients/        # 非同步客戶端
│   ├── base.py     # AsyncModbusClientBase 抽象介面
│   ├── client.py   # TCP/RTU/Shared 實作
│   ├── queue.py    # 請求佇列 + 背景 Worker（優先權排程 + 斷路器）
│   └── compat.py   # pymodbus 版本相容層
├── _pymodbus.py    # pymodbus server 元件 lazy import 工具
├── codec.py        # ModbusCodec 編解碼器
├── config.py       # 連線設定 (TCP/RTU)
├── enums.py        # 列舉定義
└── exceptions.py   # 例外類別
```

---

## Dataview

```dataview
TABLE WITHOUT ID
  file.link AS "頁面",
  tags AS "標籤"
FROM "03-Modbus"
WHERE file.name != "_MOC Modbus"
SORT file.name ASC
```

---

## 相關模組

| 方向 | 模組 |
|------|------|
| 上游 | [[_MOC Core]] — 核心生命週期與基礎工具 |
| 下游 | [[_MOC Equipment]] — 設備抽象層，基於 Modbus 建構 |
