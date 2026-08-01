from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # Без аргументов — сразу окошко
    if not args:
        from .gui import run_gui

        return run_gui()
    if args[0] == "gui":
        from .gui import run_gui

        return run_gui()
    from .cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
