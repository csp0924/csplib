#!/usr/bin/env python
"""
Cross-Platform Wheel Builder for csp_lib

跨平台建置輔助工具，自動執行：
1. 複製套件到暫存目錄
2. Cython 編譯
3. 移除 .py 原始碼（保護程式碼）
4. 打包 wheel

使用方式：
    python build_wheel.py          # 建置 wheel
    python build_wheel.py clean    # 僅清理
    python build_wheel.py --help   # 顯示說明
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# =============== Configuration ===============

PROJECT_ROOT = Path(__file__).parent
PACKAGE_NAME = "csp_lib"
BUILD_DIRS = ["build", "dist", f"{PACKAGE_NAME}.egg-info", "csp0924_lib.egg-info"]

# Cython 產生的中間檔案副檔名
GENERATED_EXTENSIONS = {".c", ".pyd", ".so", ".html"}

# 建置時需要複製的檔案
BUILD_FILES = ["setup.py", "pyproject.toml", "README.md", "LICENSE"]


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
        if shutil.which("cl"):
            print("[OK] MSVC compiler (cl.exe) found")
        else:
            # 嘗試透過 vswhere 檢查 Visual Studio 是否安裝
            vswhere = (
                Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            )
            if vswhere.exists():
                vs_result = subprocess.run(
                    [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
                    capture_output=True,
                    text=True,
                )
                if vs_result.returncode == 0 and vs_result.stdout.strip():
                    print(f"[OK] Visual Studio found: {vs_result.stdout.strip()}")
                    print("     Note: Run from 'Developer Command Prompt' to ensure cl.exe is in PATH")
                else:
                    print("[X] Visual Studio Build Tools not found.")
                    print("    Install from: https://visualstudio.microsoft.com/visual-cpp-build-tools/")
                    print("    Select 'Desktop development with C++' workload")
                    return False
            else:
                print("[WARN] Cannot verify MSVC installation (cl.exe not in PATH, vswhere not found)")
                print("       Ensure Visual Studio Build Tools is installed with C++ workload")
                print("       Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/")
    else:
        # Linux/macOS 檢查 gcc
        result = subprocess.run(["gcc", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("[OK] GCC found")
        else:
            print("[X] GCC not found. Install build-essential (Ubuntu) or gcc")
            return False

    return True


def copy_to_temp(temp_dir: Path) -> None:
    """
    複製套件和建置檔案到暫存目錄

    Args:
        temp_dir: 暫存目錄路徑
    """
    print("=" * 50)
    print(f"Copying to temp directory: {temp_dir}")
    print("=" * 50)

    # 複製套件目錄
    src_package = PROJECT_ROOT / PACKAGE_NAME
    dst_package = temp_dir / PACKAGE_NAME
    shutil.copytree(
        src_package,
        dst_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyd", "*.so", "*.c"),
    )
    print(f"Copied: {PACKAGE_NAME}/")

    # 複製建置檔案
    for filename in BUILD_FILES:
        src_file = PROJECT_ROOT / filename
        if src_file.exists():
            shutil.copy2(src_file, temp_dir / filename)
            print(f"Copied: {filename}")

    print()


def build_extensions(build_dir: Path) -> bool:
    """
    在指定目錄執行 Cython 編譯

    Args:
        build_dir: 建置目錄

    Returns:
        是否成功
    """
    print("=" * 50)
    print("Building Cython extensions...")
    print("=" * 50)

    result = subprocess.run(
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        cwd=build_dir,
    )

    if result.returncode != 0:
        print("Build failed! Check the compiler output above for details.")
        return False

    # 驗證編譯產物
    package_dir = build_dir / PACKAGE_NAME
    ext = ".pyd" if sys.platform == "win32" else ".so"
    compiled_files = list(package_dir.rglob(f"*{ext}"))
    if not compiled_files:
        print(f"Build failed! No compiled extensions ({ext}) found after build.")
        return False

    print(f"Build completed! ({len(compiled_files)} extensions compiled)\n")
    return True


def generate_stubs(build_dir: Path) -> bool:
    """
    使用 stubgen 生成 .pyi stub 檔案

    Args:
        build_dir: 建置目錄

    Returns:
        是否成功
    """
    print("=" * 50)
    print("Generating .pyi stub files...")
    print("=" * 50)

    # 檢查 mypy 是否安裝
    try:
        import mypy.stubgen  # noqa: F401

        print("[OK] mypy.stubgen available")
    except ImportError:
        print("[SKIP] mypy not installed, skipping stub generation")
        print("Install with: pip install mypy")
        return True

    # 安裝 optional dependencies 以便 stubgen 能分析所有模組
    # 使用專案根目錄的 pyproject.toml
    print("Installing optional dependencies for stub generation...")
    install_result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", ".[all]"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if install_result.returncode != 0:
        print(f"[WARN] Failed to install optional deps: {install_result.stderr}")

    package_dir = build_dir / PACKAGE_NAME

    # 使用 stubgen 對整個套件生成 stub
    # stubgen 是 mypy 安裝時提供的命令
    # --inspect-mode: 實際 import 模組，產生更準確的簽名
    print("Running stubgen with --inspect-mode...")
    result = subprocess.run(
        [
            "stubgen",
            "-o",
            str(build_dir),
            "--include-private",
            "--inspect-mode",
            "-p",
            PACKAGE_NAME,
        ],
        cwd=build_dir,
        capture_output=True,
        text=True,
    )

    # 顯示 stubgen 輸出
    if result.stdout:
        print(f"stubgen output: {result.stdout}")
    if result.returncode != 0:
        print(f"stubgen stderr: {result.stderr}")
        print("Continuing without complete stubs...")

    # 統計生成的 stub 數量
    stub_count = len(list(package_dir.rglob("*.pyi")))
    print(f"Generated {stub_count} stub files\n")
    return True


def remove_source_files(build_dir: Path) -> None:
    """
    移除 .py 原始碼檔案和 .c 中間檔案（保留 __init__.py）

    Args:
        build_dir: 建置目錄
    """
    print("=" * 50)
    print("Removing source files (keeping __init__.py)...")
    print("=" * 50)

    package_dir = build_dir / PACKAGE_NAME
    removed_count = 0

    for py_file in package_dir.rglob("*.py"):
        # 保留 __init__.py
        if py_file.name == "__init__.py":
            continue

        # 檢查是否有對應的 .pyd 或 .so 檔案
        stem = py_file.stem
        parent = py_file.parent
        has_binary = any(parent.glob(f"{stem}*.pyd")) or any(parent.glob(f"{stem}*.so"))

        if has_binary:
            print(f"Removing: {py_file.relative_to(build_dir)}")
            py_file.unlink()
            removed_count += 1

    # 移除 .c 中間檔案
    for c_file in package_dir.rglob("*.c"):
        print(f"Removing: {c_file.relative_to(build_dir)}")
        c_file.unlink()
        removed_count += 1

    print(f"Removed {removed_count} source files\n")


def build_wheel(build_dir: Path) -> bool:
    """
    打包 wheel

    Args:
        build_dir: 建置目錄

    Returns:
        是否成功
    """
    print("=" * 50)
    print("Building wheel...")
    print("=" * 50)

    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel"],
        cwd=build_dir,
    )

    if result.returncode != 0:
        print("Wheel build failed! Check the build output above for details.")
        return False

    print("Wheel build completed!\n")
    return True


def copy_dist_to_project(temp_dir: Path) -> None:
    """
    將產生的 wheel 複製回專案目錄

    Args:
        temp_dir: 暫存目錄
    """
    temp_dist = temp_dir / "dist"
    project_dist = PROJECT_ROOT / "dist"

    if not temp_dist.exists():
        print("Warning: No dist directory found in temp")
        return

    # 確保專案 dist 目錄存在
    project_dist.mkdir(exist_ok=True)

    # 複製 wheel 檔案
    for whl_file in temp_dist.glob("*.whl"):
        dst_file = project_dist / whl_file.name
        shutil.copy2(whl_file, dst_file)
        print(f"Copied to: {dst_file.relative_to(PROJECT_ROOT)}")


# =============== Main Entry ===============


def main():
    parser = argparse.ArgumentParser(description="Build csp_lib as binary wheel package")
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
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temp directory after build (for debugging)",
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

    # 在暫存目錄中建置
    with tempfile.TemporaryDirectory(prefix="csp_build_", delete=not args.keep_temp) as temp_str:
        temp_dir = Path(temp_str)

        if args.keep_temp:
            print(f"Temp directory (kept): {temp_dir}\n")

        # 1. 複製到暫存目錄
        copy_to_temp(temp_dir)

        # 2. 生成 .pyi stub 檔案 (在 Cython 編譯前，使用 .py 原始碼)
        generate_stubs(temp_dir)

        # 3. Cython 編譯
        if not build_extensions(temp_dir):
            return 1

        # 4. 移除 .py 原始碼
        remove_source_files(temp_dir)

        # 5. 打包 wheel
        if not build_wheel(temp_dir):
            return 1

        # 6. 複製 wheel 回專案
        copy_dist_to_project(temp_dir)

    print("=" * 50)
    print("SUCCESS! Wheel package ready in dist/")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
