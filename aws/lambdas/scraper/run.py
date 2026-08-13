"""Standalone entry point for Railway (non-Lambda) execution."""
import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in [str(_HERE), str(_HERE.parent / "shared")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from handler import _main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(_main())
