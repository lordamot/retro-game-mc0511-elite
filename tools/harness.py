#!/usr/bin/env python3
"""Time 100 fixed-scene drawing frames; accepts bench.py's scene options."""
import sys
from bench import main

if __name__ == "__main__":
    raise SystemExit(main(["--fixed", "--draw-frames", "100"] + sys.argv[1:]))
