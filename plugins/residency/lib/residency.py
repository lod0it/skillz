#!/usr/bin/env python3
"""residency - see and trim what Claude Code keeps resident in context (zero tokens)."""
import argparse
import sys
from pathlib import Path


def version():
    return (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="residency", description=__doc__)
    ap.add_argument("--version", action="version", version=version())
    ap.parse_args(argv)
    print("not implemented yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
