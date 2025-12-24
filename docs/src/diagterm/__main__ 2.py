from __future__ import annotations

import argparse

from diagterm.app import DiagTermApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="diagterm")
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        help="Refresh interval in seconds (default: 1.0)",
    )
    args = parser.parse_args()

    DiagTermApp(refresh_interval=args.refresh).run()


if __name__ == "__main__":
    main()
