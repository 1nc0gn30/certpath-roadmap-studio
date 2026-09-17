"""Main module entrypoint for certpath-roadmap-studio."""

from __future__ import annotations

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
