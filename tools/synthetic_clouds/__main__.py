"""``python -m tools.synthetic_clouds`` entry point."""

from __future__ import annotations

import sys

from tools.synthetic_clouds.cli import main

if __name__ == "__main__":
    sys.exit(main())
