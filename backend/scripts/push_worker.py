#!/usr/bin/env python3
"""Run with: ./scripts/uv.sh run python scripts/push_worker.py --once"""

from app.basic.push_worker import main

if __name__ == "__main__":
    raise SystemExit(main())
