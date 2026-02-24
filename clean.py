"""
Cython Build Cleanup Script

清理 Cython 編譯產生的暫存檔案。
執行方式：python clean.py
"""

import shutil
from pathlib import Path

# =============== Configuration ===============

PACKAGE_ROOT = Path(__file__).parent
PACKAGE_NAME = "csp_lib"

# Cython 產生的檔案副檔名
CYTHON_EXTENSIONS = {".c", ".pyd", ".so", ".html"}

# 需要刪除的目錄
DIRECTORIES_TO_REMOVE = [
    "build",
    "dist",
    "wheels",
    f"{PACKAGE_NAME}.egg-info",
]


# =============== Cleanup Functions ===============


def clean_cython_files() -> int:
    """
    清理 Cython 編譯產生的 .c, .pyd, .so, .html 檔案

    Returns:
        刪除的檔案數量
    """
    package_dir = PACKAGE_ROOT / PACKAGE_NAME
    deleted_count = 0

    for ext in CYTHON_EXTENSIONS:
        for filepath in package_dir.rglob(f"*{ext}"):
            print(f"  Deleting: {filepath.relative_to(PACKAGE_ROOT)}")
            filepath.unlink()
            deleted_count += 1

    return deleted_count


def clean_directories() -> int:
    """
    清理建置目錄

    Returns:
        刪除的目錄數量
    """
    deleted_count = 0

    for dirname in DIRECTORIES_TO_REMOVE:
        dirpath = PACKAGE_ROOT / dirname
        if dirpath.exists():
            print(f"  Removing directory: {dirname}/")
            shutil.rmtree(dirpath)
            deleted_count += 1

    return deleted_count


def clean_pycache() -> int:
    """
    清理 __pycache__ 目錄

    Returns:
        刪除的目錄數量
    """
    deleted_count = 0

    for cache_dir in PACKAGE_ROOT.rglob("__pycache__"):
        print(f"  Removing: {cache_dir.relative_to(PACKAGE_ROOT)}/")
        shutil.rmtree(cache_dir)
        deleted_count += 1

    return deleted_count


# =============== Main ===============


def main():
    """執行清理"""
    print("=" * 50)
    print("Cython Build Cleanup")
    print("=" * 50)

    print("\n[1/3] Cleaning Cython generated files...")
    file_count = clean_cython_files()
    print(f"      → Deleted {file_count} file(s)")

    print("\n[2/3] Cleaning build directories...")
    dir_count = clean_directories()
    print(f"      → Removed {dir_count} directory(ies)")

    print("\n[3/3] Cleaning __pycache__...")
    cache_count = clean_pycache()
    print(f"      → Removed {cache_count} directory(ies)")

    print("\n" + "=" * 50)
    print("✓ Cleanup complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
