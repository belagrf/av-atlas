#!/usr/bin/env python3
"""Convenience wrapper for the installed fixture generator."""

import sys
from pathlib import Path

from av_atlas.fixture import make_fixture

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_synthetic_fixture.py OUTPUT_DIRECTORY")
    print(make_fixture(Path(sys.argv[1])))
