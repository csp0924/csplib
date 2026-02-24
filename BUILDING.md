# Building csp_lib Binary Distribution

本文件說明如何將 `csp_lib` 編譯為二進位 wheel 套件。

## 環境需求

### Python 版本
- Python 3.13+

### C 編譯器

#### Windows
安裝 **Visual Studio Build Tools**:
1. 下載 [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. 安裝時選擇 "Desktop development with C++"

#### Rocky Linux / Ubuntu
```bash
# Rocky Linux
sudo dnf groupinstall "Development Tools"
sudo dnf install python3-devel

# Ubuntu
sudo apt update
sudo apt install build-essential python3-dev
```

### Python 依賴
```bash
pip install cython build
```

---

## 建置指令

### 使用建置腳本 (推薦)

```bash
# 完整建置流程
python build_wheel.py

# 僅清理建置產物
python build_wheel.py clean

# 檢查建置環境
python build_wheel.py check
```

### 手動建置

```bash
# 1. 清理舊產物
rm -rf build dist *.egg-info

# 2. 編譯 Cython 擴展
python setup.py build_ext --inplace

# 3. 打包 wheel
python -m build --wheel
```

---

## 輸出檔案

建置完成後，wheel 檔案位於 `dist/` 目錄：

```
dist/
└── csp_lib-0.1.0-cp313-cp313-win_amd64.whl   # Windows
└── csp_lib-0.1.0-cp313-cp313-linux_x86_64.whl # Linux
```

### 安裝方式

```bash
pip install dist/csp_lib-*.whl
```

---

## 跨平台建置

wheel 是平台相關的，需在各目標平台分別建置：

| 平台 | wheel 檔名範例 |
|------|---------------|
| Windows x64 | `csp_lib-0.1.0-cp313-cp313-win_amd64.whl` |
| Rocky Linux x64 | `csp_lib-0.1.0-cp313-cp313-linux_x86_64.whl` |
| Ubuntu x64 | `csp_lib-0.1.0-cp313-cp313-linux_x86_64.whl` |

---

## 常見問題

### Q: 編譯時出現 "Python.h not found"
安裝 Python 開發套件：
```bash
# Rocky Linux
sudo dnf install python3-devel

# Ubuntu  
sudo apt install python3-dev
```

### Q: Windows 編譯失敗
確認已安裝 Visual Studio Build Tools，並使用 "Developer Command Prompt" 執行建置。

### Q: 如何驗證 wheel 內容？
```bash
# 列出 wheel 內容
unzip -l dist/csp_lib-*.whl

# 確認包含 .pyd/.so 檔案，不包含 .py 原始碼
```
