#!/usr/bin/env python3
"""
Build script for HTopWin.
Runs PyInstaller to produce dist/HTopWin/HTopWin.exe
"""
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist" / "HTopWin"
EXE = DIST / "HTopWin.exe"


def main():
    print("=== Building HTopWin EXE ===")

    # Clean previous build
    for d in [ROOT / "build", ROOT / "dist"]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Cleaned: {d}")

    # Run PyInstaller
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "htopwin.spec", "--noconfirm"],
        cwd=ROOT,
    )

    if result.returncode != 0:
        print("\nBuild FAILED.")
        sys.exit(1)

    if EXE.exists():
        size_mb = EXE.stat().st_size / 1_048_576
        print(f"\nBuild SUCCESS!")
        print(f"  EXE: {EXE}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"\nTo run: {EXE}")
        print(f"To distribute: zip the entire dist/HTopWin/ folder")
    else:
        print(f"\nBuild finished but EXE not found at expected path: {EXE}")


if __name__ == "__main__":
    main()
