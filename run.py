"""PyInstaller entry point.

PyInstaller can't target `python -m claude_meter` directly, so it builds this
one-line shim instead.
"""

from claude_meter.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
