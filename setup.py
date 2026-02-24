"""
Cython Build Script for csp_lib

此腳本負責將 Python 原始碼編譯為二進位擴展模組 (.pyd/.so)。
執行方式：python setup.py build_ext --inplace

環境變數：
    SKIP_CYTHON: 設為 "1" 跳過 Cython 編譯 (用於 CI 測試)
"""

import os
import sys
from pathlib import Path

from setuptools import setup

# 檢查是否跳過 Cython 編譯
SKIP_CYTHON = os.environ.get("SKIP_CYTHON", "0") == "1"

if SKIP_CYTHON:
    print("SKIP_CYTHON=1: Skipping Cython compilation")
    setup(name="csp_lib", ext_modules=[], zip_safe=False)
    # 提前退出，不執行後續編譯邏輯
    sys.exit(0)

# =============== Cython Build (僅在非 SKIP 模式執行) ===============

from Cython.Build import cythonize
from setuptools import Extension

# =============== Configuration ===============

# 套件根目錄
PACKAGE_ROOT = Path(__file__).parent
PACKAGE_NAME = "csp_lib"

# 排除不編譯的檔案 (保留為純 Python)
EXCLUDED_FILES = {
    "__init__.py",  # 套件初始化檔案必須保留
}

# 排除的目錄
EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "tests",
    "build",
    "dist",
    "static",
}


# =============== Helper Functions ===============


def find_pyx_and_py_files() -> list[Path]:
    """
    掃描套件目錄，找出需要編譯的 .py 和 .pyx 檔案

    Returns:
        需要編譯的檔案路徑列表
    """
    package_dir = PACKAGE_ROOT / PACKAGE_NAME
    files_to_compile: list[Path] = []

    for root, dirs, files in os.walk(package_dir):
        # 過濾排除的目錄
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for filename in files:
            # 跳過排除的檔案
            if filename in EXCLUDED_FILES:
                continue

            # 收集 .py 和 .pyx 檔案
            if filename.endswith((".py", ".pyx")):
                filepath = Path(root) / filename
                files_to_compile.append(filepath)

    return files_to_compile


def create_extensions(files: list[Path]) -> list[Extension]:
    """
    為每個檔案建立 Extension 物件

    Args:
        files: 要編譯的檔案列表

    Returns:
        Extension 物件列表
    """
    extensions: list[Extension] = []

    for filepath in files:
        # 計算模組名稱 (例如: csp_lib.modbus.enums)
        relative_path = filepath.relative_to(PACKAGE_ROOT)
        module_name = str(relative_path.with_suffix("")).replace(os.sep, ".")

        ext = Extension(
            name=module_name,
            sources=[str(filepath)],
            # 編譯優化選項
            extra_compile_args=_get_compile_args(),
        )
        extensions.append(ext)

    return extensions


def _get_compile_args() -> list[str]:
    """取得平台相關的編譯參數"""
    if sys.platform == "win32":
        return ["/O2"]  # Windows MSVC 優化
    else:
        return ["-O3", "-fPIC"]  # Linux/macOS GCC 優化


# =============== Main Setup ===============

# 找出要編譯的檔案
_files = find_pyx_and_py_files()

if not _files:
    print("Warning: No files found to compile!")
    # 仍須呼叫 setup()，否則 build backend 會失敗
    _ext_modules = []
else:
    print(f"Found {len(_files)} files to compile:")
    for _f in _files:
        print(f"  - {_f.relative_to(PACKAGE_ROOT)}")
    _ext_modules = cythonize(
        create_extensions(_files),
        compiler_directives={
            "language_level": "3",  # Python 3 語法
            "boundscheck": False,  # 關閉邊界檢查 (效能優化)
            "wraparound": False,  # 關閉負索引支援 (效能優化)
        },
        # 不產生 annotation HTML
        annotate=False,
    )

# 必須在 module level 呼叫 setup()，build backend 需要這個
setup(
    name=PACKAGE_NAME,
    ext_modules=_ext_modules,
    zip_safe=False,
)
