#!/usr/bin/env python
"""
Cross-Platform Wheel Builder for csp_lib

跨平台建置輔助工具，自動執行：
1. 清理舊建置產物
2. Cython 編譯
3. 打包 wheel

使用方式：
    python build_wheel.py          # 建置 wheel
    python build_wheel.py clean    # 僅清理
    python build_wheel.py --help   # 顯示說明
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# =============== Configuration ===============

PROJECT_ROOT = Path(__file__).parent
PACKAGE_NAME = "csp_lib"
BUILD_DIRS = ["build", "dist", f"{PACKAGE_NAME}.egg-info"]

# Cython 產生的中間檔案副檔名
GENERATED_EXTENSIONS = {".c", ".pyd", ".so", ".html"}


# =============== Clean Functions ===============


def clean_build_dirs() -> None:
    """清理建置目錄"""
    for dir_name in BUILD_DIRS:
        dir_path = PROJECT_ROOT / dir_name
        if dir_path.exists():
            print(f"Removing: {dir_path}")
            shutil.rmtree(dir_path)


def clean_generated_files() -> None:
    """清理 Cython 產生的中間檔案"""
    package_dir = PROJECT_ROOT / PACKAGE_NAME

    for ext in GENERATED_EXTENSIONS:
        for filepath in package_dir.rglob(f"*{ext}"):
            # 保留 __pycache__ 目錄中的檔案由 Python 管理
            if "__pycache__" not in str(filepath):
                print(f"Removing: {filepath.relative_to(PROJECT_ROOT)}")
                filepath.unlink()


def clean_all() -> None:
    """執行完整清理"""
    print("=" * 50)
    print("Cleaning build artifacts...")
    print("=" * 50)
    clean_build_dirs()
    clean_generated_files()
    print("Clean completed!\n")


# =============== Build Functions ===============


def check_requirements() -> bool:
    """檢查建置需求"""
    try:
        import Cython  # noqa: F401

        print(f"[OK] Cython version: {Cython.__version__}")
    except ImportError:
        print("[X] Cython not found. Install with: pip install cython")
        return False

    # 檢查 C 編譯器
    if sys.platform == "win32":
        # Windows 需要 Visual Studio Build Tools
        print("Note: Windows requires Visual Studio Build Tools")
    else:
        # Linux/macOS 檢查 gcc
        result = subprocess.run(
            ["gcc", "--version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("[OK] GCC found")
        else:
            print("[X] GCC not found. Install build-essential (Ubuntu) or gcc")
            return False

    return True


def build_extensions() -> bool:
    """
    執行 Cython 編譯

    Returns:
        是否成功
    """
    print("=" * 50)
    print("Building Cython extensions...")
    print("=" * 50)

    result = subprocess.run(
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:
        print("Build failed!")
        return False

    print("Build completed!\n")
    return True


def build_wheel() -> bool:
    """
    打包 wheel

    Returns:
        是否成功
    """
    print("=" * 50)
    print("Building wheel...")
    print("=" * 50)

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel"],
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:
        print("Wheel build failed!")
        return False

    # 顯示產生的 wheel 檔案
    dist_dir = PROJECT_ROOT / "dist"
    if dist_dir.exists():
        wheels = list(dist_dir.glob("*.whl"))
        if wheels:
            print("\nGenerated wheel files:")
            for whl in wheels:
                print(f"  - {whl.name}")

    print("Wheel build completed!\n")
    return True


# =============== Main Entry ===============


def main():
    parser = argparse.ArgumentParser(
        description="Build csp_lib as binary wheel package"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="build",
        choices=["build", "clean", "check"],
        help="Action to perform (default: build)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip cleaning before build",
    )

    args = parser.parse_args()

    if args.action == "clean":
        clean_all()
        return 0

    if args.action == "check":
        return 0 if check_requirements() else 1

    # Build action
    print("=" * 50)
    print(f"Building {PACKAGE_NAME} binary wheel")
    print(f"Platform: {sys.platform}")
    print(f"Python: {sys.version}")
    print("=" * 50 + "\n")

    if not check_requirements():
        return 1

    if not args.no_clean:
        clean_all()

    if not build_extensions():
        return 1

    if not build_wheel():
        return 1

    print("=" * 50)
    print("SUCCESS! Wheel package ready in dist/")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
