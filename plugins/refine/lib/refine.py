#!/usr/bin/env python3
"""refine: dispatcher for the code-improvement helpers.

Each subcommand lives in its own module under lib/, imported lazily so that
modules can be added without touching this file.
"""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMANDS = {"golden": "golden", "measure": "measure", "coverage": "coverage_map"}

USAGE = """usage: refine <command> [args]

commands:
  golden     record and compare golden outputs
  measure    measure code before and after a change
  coverage   map which code the tests cover

options:
  --version  print the plugin version
  -h, --help show this text
"""


def version():
    return (HERE.parent / "VERSION").read_text(encoding="utf-8").strip()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, end="")
        return 0 if argv else 2
    if argv[0] == "--version":
        print(version())
        return 0
    name = argv[0]
    if name not in COMMANDS:
        print(f"refine: unknown command '{name}'\n", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        return 2
    modname = COMMANDS[name]
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    try:
        module = importlib.import_module(modname)
    except ModuleNotFoundError as e:
        if e.name != modname:
            raise
        print(f"{name}: not implemented yet", file=sys.stderr)
        return 2
    return module.main(argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main())
